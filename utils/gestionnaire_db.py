"""
Gestionnaire de la base de données Eau Vive.

Ne crée PAS les tables : utiliser `utils.schema_db` pour l'initialisation.
Ce module suppose que le schéma existe déjà.
"""
import sqlite3
import json
import os
import re
import threading
import unicodedata
from datetime import datetime


# =====================================================================
#  Utilitaires génériques
# =====================================================================
def nettoyer_nom_fichier(nom):
    """Nettoie un nom (retire accents et remplace espaces par _)."""
    if not isinstance(nom, str):
        return str(nom)
    nom = unicodedata.normalize("NFD", nom)
    nom = "".join(c for c in nom if unicodedata.category(c) != "Mn")
    nom = nom.replace(" ", "_")
    nom = re.sub(r'[<>:"/\\|?*]', "_", nom)
    return nom


# =====================================================================
#  Gestionnaire
# =====================================================================
class GestionnaireDB:
    def __init__(self, db_path="EauVive_prix.db"):
        """Initialise la connexion à la base de données existante.

        Raises:
            FileNotFoundError: si la base n'existe pas.
        """
        if not os.path.exists(db_path):
            raise FileNotFoundError(
                f"La base '{db_path}' n'existe pas. "
                f"Initialisez-la avec : python -m utils.schema_db {db_path}"
            )

        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._lock = threading.Lock()
        self._verifier_schema()

    # ------------------------------------------------------------------
    def _verifier_schema(self):
        """Vérifie que les tables essentielles existent."""
        conn, cursor = self._get_connection()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        requises = {"PRODUITS", "RELEVES_PRIX", "MAGASINS", "CATEGORIES"}
        manquantes = requises - tables
        if manquantes:
            raise RuntimeError(
                f"Tables manquantes dans la base : {manquantes}. "
                f"Exécutez : python -m utils.schema_db {self.db_path}"
            )

    # ------------------------------------------------------------------
    def _get_connection(self):
        """Obtient une connexion pour le thread courant."""
        with self._lock:
            if self.conn is None:
                self.conn = sqlite3.connect(
                    self.db_path, check_same_thread=False
                )
                self.cursor = self.conn.cursor()
            return self.conn, self.cursor

    # ------------------------------------------------------------------
    #  Utilitaires
    # ------------------------------------------------------------------
    def get_magasin_id(self, nom):
        """Récupère l'ID d'un magasin par son nom (nomcsv ou nom)."""
        conn, cursor = self._get_connection()
        cursor.execute(
            "SELECT id FROM MAGASINS WHERE nomcsv = ? OR nom = ?",
            (nom, nom)
        )
        result = cursor.fetchone()
        if result:
            return result[0]

        cursor.execute("SELECT id, nom, nomcsv FROM MAGASINS")
        for row in cursor.fetchall():
            mag_id, mag_nom, mag_nomcsv = row
            if nettoyer_nom_fichier(mag_nom) == nom or (
                mag_nomcsv and nettoyer_nom_fichier(mag_nomcsv) == nom
            ):
                return mag_id
        return None

    def get_categorie_id(self, nom):
        """Récupère l'ID d'une catégorie par son nom."""
        conn, cursor = self._get_connection()
        cursor.execute("SELECT id FROM CATEGORIES WHERE nom = ?", (nom,))
        result = cursor.fetchone()
        return result[0] if result else None

    def creer_categorie(self, nom, parent_id=None):
        """Crée une catégorie si elle n'existe pas et retourne son id."""
        conn, cursor = self._get_connection()
        cursor.execute(
            "INSERT OR IGNORE INTO CATEGORIES (nom, parent_id) VALUES (?, ?)",
            (nom, parent_id)
        )
        conn.commit()
        return self.get_categorie_id(nom)

    @staticmethod
    def _normaliser_prix(prix):
        """Normalise un prix ('10.75€', '1,25', 10.75) -> '10.75'."""
        if prix is None:
            return ''
        if isinstance(prix, (int, float)):
            return f"{prix:.2f}"
        s = str(prix).strip()
        s = re.sub(r'[^\d.,]', '', s).replace(',', '.')
        return s

    @staticmethod
    def _tags_vers_texte(tags):
        """Convertit une liste de tags (dicts ou strings) en texte lisible."""
        if not tags:
            return ''
        if not isinstance(tags, list):
            return str(tags)
        resultats = []
        for tag in tags:
            if isinstance(tag, dict):
                resultats.append(str(tag.get('text', '')))
            else:
                resultats.append(str(tag))
        return '; '.join(r for r in resultats if r)

    # ------------------------------------------------------------------
    #  Extraction des métadonnées depuis le nom de fichier
    # ------------------------------------------------------------------
    @staticmethod
    def _valider_date_yymmdd(date_str):
        """Valide une chaîne YYMMDD et la convertit en YYYY-MM-DD."""
        if not re.fullmatch(r'\d{6}', date_str):
            return None
        try:
            yy = int(date_str[0:2])
            mm = int(date_str[2:4])
            dd = int(date_str[4:6])
            annee = 2000 + yy
            datetime(annee, mm, dd)
            return f"{annee:04d}-{mm:02d}-{dd:02d}"
        except (ValueError, IndexError):
            return None

    def extraire_metadonnees_fichier(self, fichier_path):
        """Extrait (magasin, date, catégorie) depuis :
            V6_<Magasin>_<YYMMDD>_<Catégorie>.json
        """
        nom_fichier = os.path.basename(fichier_path)
        if not nom_fichier.lower().endswith(".json"):
            return None, None, None

        nom_sans_extension = nom_fichier[:-5]
        if not nom_sans_extension.startswith("V6_"):
            return None, None, None

        reste = nom_sans_extension[3:]
        motif = re.compile(r'(?<=_)(\d{6})(?=_|$)')
        date_str = None
        date_debut = None

        for m in motif.finditer(reste):
            candidat = m.group(1)
            if self._valider_date_yymmdd(candidat) is not None:
                date_str = candidat
                date_debut = m.start(1)
                break

        if date_str is None:
            return None, None, None

        date_releve = self._valider_date_yymmdd(date_str)
        nom_magasin = reste[:date_debut - 1].strip()
        fin_date = date_debut + len(date_str)
        nom_categorie = reste[fin_date:].lstrip('_').strip()

        if not nom_magasin or not nom_categorie:
            return None, None, None

        return nom_magasin, date_releve, nom_categorie

    # ------------------------------------------------------------------
    #  Import produit / relevé
    # ------------------------------------------------------------------
    def importer_produit_json(self, item, categorie_id=None):
        """Importe un produit depuis un dict JSON."""
        try:
            code_interne = str(item.get('ref_id', '')).strip()
            if not code_interne:
                return False

            conn, cursor = self._get_connection()

            description = (item.get('description') or '').strip()
            if not description:
                description = f"Produit {code_interne}"
                print(f"⚠️ Description manquante pour le produit {code_interne}")

            ean = (item.get('ean') or '').strip()
            marque = (item.get('marque') or '').strip()
            volume = (item.get('volume') or '').strip()

            lien_fiche = (item.get('lien') or '').strip()
            if lien_fiche and not lien_fiche.startswith('http'):
                lien_fiche = f"https://eau-vive.com{lien_fiche}"

            url_img = (item.get('url_img') or item.get('img') or '').strip()
            caracteristique = self._tags_vers_texte(item.get('tags', []))

            cursor.execute(
                "SELECT id FROM PRODUITS WHERE code_interne = ?",
                (code_interne,)
            )
            existe = cursor.fetchone()

            if existe:
                cursor.execute('''
                    UPDATE PRODUITS SET
                        ean             = COALESCE(NULLIF(?, ''), ean),
                        description     = COALESCE(NULLIF(?, ''), description),
                        marque          = COALESCE(NULLIF(?, ''), marque),
                        volume          = COALESCE(NULLIF(?, ''), volume),
                        lien_fiche      = COALESCE(NULLIF(?, ''), lien_fiche),
                        caracteristique = COALESCE(NULLIF(?, ''), caracteristique),
                        url_img         = COALESCE(NULLIF(?, ''), url_img),
                        categorie_id    = CASE
                            WHEN categorie_id IS NULL OR categorie_id = 10
                                THEN COALESCE(?, categorie_id)
                            ELSE categorie_id
                        END
                    WHERE code_interne = ?
                ''', (ean, description, marque, volume, lien_fiche,
                      caracteristique, url_img, categorie_id, code_interne))
            else:
                cursor.execute('''
                    INSERT INTO PRODUITS (
                        code_interne, ean, description, marque, volume,
                        lien_fiche, caracteristique, url_img, categorie_id,
                        ean_valide, date_validation
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    code_interne, ean, description, marque, volume,
                    lien_fiche, caracteristique, url_img, categorie_id,
                    0, None
                ))

            self.detecter_conflits_ean(code_interne, ean)
            return True

        except Exception as e:
            print(f"❌ Erreur import produit {item.get('ref_id', '?')}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def importer_releve_prix_json(self, item, magasin_id, date_releve=None):
        """Importe un relevé de prix depuis un dict JSON."""
        try:
            code_interne = str(item.get('ref_id', '')).strip()
            if not code_interne:
                return False

            conn, cursor = self._get_connection()
            cursor.execute(
                "SELECT id FROM PRODUITS WHERE code_interne = ?",
                (code_interne,)
            )
            result = cursor.fetchone()
            if not result:
                return False
            produit_id = result[0]

            prix = self._normaliser_prix(item.get('prix', ''))
            prix_old = self._normaliser_prix(item.get('ancien_prix', ''))
            prix_unit = (item.get('volume_price') or '').strip()

            if date_releve is None:
                date_releve = datetime.now().strftime('%Y-%m-%d')

            cursor.execute('''
                INSERT OR IGNORE INTO RELEVES_PRIX (
                    produit_id, magasin_id, date_releve,
                    prix, prix_old, prix_unit
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                produit_id, magasin_id, date_releve,
                str(prix), str(prix_old), str(prix_unit)
            ))
            return True

        except Exception as e:
            print(f"❌ Erreur relevé pour {item.get('ref_id', '?')}: {e}")
            return False

    # ------------------------------------------------------------------
    #  Import d'un fichier JSON complet
    # ------------------------------------------------------------------
    def importer_fichier_json(self, fichier_path, magasin_id=None, callback=None):
        """Importe un fichier JSON complet."""
        if not os.path.exists(fichier_path):
            msg = f"Fichier {fichier_path} non trouvé"
            if callback:
                callback(msg, 'error')
            return False

        try:
            nom_magasin, date_releve, nom_famille = \
                self.extraire_metadonnees_fichier(fichier_path)
            if nom_magasin is None:
                msg = (f"Format de nom invalide (attendu : "
                       f"V5_<Magasin>_<YYMMDD>_<Catégorie>.json) : "
                       f"{os.path.basename(fichier_path)}")
                if callback:
                    callback(msg, 'error')
                return False

            if magasin_id is None:
                magasin_id = self.get_magasin_id(nom_magasin)
                if magasin_id is None:
                    magasin_id = self.creer_magasin(nom_magasin, nomcsv=nom_magasin)
                if magasin_id is None:
                    msg = f"Magasin '{nom_magasin}' introuvable."
                    if callback:
                        callback(msg, 'error')
                    return False

            categorie_id = self.get_categorie_id(nom_famille)
            if categorie_id is None:
                categorie_id = self.creer_categorie(nom_famille)

            with open(fichier_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, dict):
                for cle in ('produits', 'products', 'items', 'data'):
                    if cle in data and isinstance(data[cle], list):
                        data = data[cle]
                        break
                else:
                    data = [data]

            if not isinstance(data, list):
                msg = "Le JSON doit contenir une liste de produits."
                if callback:
                    callback(msg, 'error')
                return False

            print(f"\n📁 Lecture : {os.path.basename(fichier_path)} "
                  f"({len(data)} entrées)")

            # Détection des références absentes (module externe)
            try:
                from utils.rapport_orphelins import (
                    detecter_references_absentes,
                    generer_rapport_orphelins,
                )
                items_absents = detecter_references_absentes(
                    data, self, callback=callback
                )
                if items_absents:
                    if callback:
                        callback(
                            f"{len(items_absents)} référence(s) absente(s) "
                            f"seront ajoutée(s).", 'info'
                        )
                    chemin_rapport = fichier_path + ".orphelins.txt"
                    try:
                        generer_rapport_orphelins(items_absents, chemin_rapport)
                        if callback:
                            callback(f"Rapport orphelins : {chemin_rapport}", 'info')
                    except Exception as e:
                        if callback:
                            callback(f"Rapport orphelins échoué : {e}", 'warning')
            except ImportError:
                # Module optionnel
                pass

            produits_importes = 0
            prix_importes = 0
            erreurs = 0
            produits_sans_description = 0
            ignores = 0

            for idx, item in enumerate(data, start=1):
                try:
                    if not isinstance(item, dict):
                        ignores += 1
                        continue
                    if not str(item.get('ref_id', '')).strip():
                        ignores += 1
                        continue
                    if not (item.get('description') or '').strip():
                        produits_sans_description += 1

                    if self.importer_produit_json(item, categorie_id):
                        produits_importes += 1
                    else:
                        erreurs += 1
                        continue

                    if self.importer_releve_prix_json(item, magasin_id, date_releve):
                        prix_importes += 1

                except Exception as e:
                    erreurs += 1
                    print(f"❌ Erreur item {idx}: {e}")

            conn, _ = self._get_connection()
            conn.commit()

            msg = (f"Importation terminée :\n"
                   f"- {produits_importes} produits importés/mis à jour\n"
                   f"- {prix_importes} relevés importés\n"
                   f"- {produits_sans_description} sans description\n"
                   f"- {ignores} ignorés\n"
                   f"- {erreurs} erreurs")
            if callback:
                callback(msg, 'success')
            return True

        except json.JSONDecodeError as e:
            if callback:
                callback(f"JSON invalide : {e}", 'error')
            return False
        except Exception as e:
            if callback:
                callback(f"Erreur : {e}", 'error')
            import traceback
            traceback.print_exc()
            return False

    # ------------------------------------------------------------------
    #  Gestion magasins / conflits / stats
    # ------------------------------------------------------------------
    def creer_magasin(self, nom, **kwargs):
        """Crée un magasin (ou le récupère s'il existe déjà)."""
        try:
            conn, cursor = self._get_connection()
            cursor.execute('''
                INSERT OR IGNORE INTO MAGASINS (
                    nom, nomcsv, adresse, code_postal, ville,
                    livraison_domicile, retrait_magasin, lien, sdv
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                nom,
                kwargs.get('nomcsv', nom),
                kwargs.get('adresse', ''),
                kwargs.get('code_postal', ''),
                kwargs.get('ville', ''),
                kwargs.get('livraison_domicile', 0),
                kwargs.get('retrait_magasin', 0),
                kwargs.get('lien', ''),
                kwargs.get('sdv', 0)
            ))
            conn.commit()
            return self.get_magasin_id(nom)
        except Exception as e:
            print(f"Erreur création magasin : {e}")
            return None

    def detecter_conflits_ean(self, code_interne, ean):
        """Détecte les conflits EAN et remplit CONFLITS_EAN."""
        if not ean:
            return
        conn, cursor = self._get_connection()

        cursor.execute(
            "SELECT id FROM PRODUITS WHERE code_interne = ?",
            (code_interne,)
        )
        produit_actuel = cursor.fetchone()
        if not produit_actuel:
            return
        produit_id_actuel = produit_actuel[0]

        cursor.execute('''
            SELECT id, code_interne FROM PRODUITS
            WHERE ean = ? AND id != ?
        ''', (ean, produit_id_actuel))
        produits_conflits = cursor.fetchall()

        for _, code_interne_conflit in produits_conflits:
            cursor.execute('''
                SELECT id FROM CONFLITS_EAN
                WHERE (code_interne_1 = ? AND code_interne_2 = ?)
                   OR (code_interne_1 = ? AND code_interne_2 = ?)
            ''', (code_interne, code_interne_conflit,
                  code_interne_conflit, code_interne))
            if not cursor.fetchone():
                date_detection = datetime.now().strftime('%Y-%m-%d')
                cursor.execute('''
                    INSERT INTO CONFLITS_EAN (
                        code_interne_1, code_interne_2, ean,
                        date_detection, statut
                    ) VALUES (?, ?, ?, ?, ?)
                ''', (code_interne, code_interne_conflit, ean,
                      date_detection, 'en_attente'))
                print(f"⚠️ Conflit EAN : {code_interne} <-> "
                      f"{code_interne_conflit} ({ean})")
        conn.commit()

    def get_statistiques(self):
        """Récupère les statistiques de la base."""
        conn, cursor = self._get_connection()
        cursor.execute("SELECT COUNT(*) FROM PRODUITS")
        nb_produits = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM RELEVES_PRIX")
        nb_releves = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM MAGASINS")
        nb_magasins = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM CATEGORIES")
        nb_categories = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM PRODUITS "
            "WHERE description IS NULL OR description = ''"
        )
        nb_sans_description = cursor.fetchone()[0]
        return {
            'produits': nb_produits,
            'releves': nb_releves,
            'magasins': nb_magasins,
            'categories': nb_categories,
            'sans_description': nb_sans_description
        }

    def verifier_produits_sans_description(self):
        """Liste les produits sans description."""
        conn, cursor = self._get_connection()
        cursor.execute("""
            SELECT code_interne, description, ean
            FROM PRODUITS
            WHERE description IS NULL OR description = ''
            LIMIT 10
        """)
        return cursor.fetchall()

    def fermer(self):
        """Ferme la connexion."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None