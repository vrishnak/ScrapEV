import sqlite3
import json
import os
import re
import sys
import argparse
import threading
import queue
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from utils.rapport_orphelins import (
    detecter_references_absentes,
    generer_rapport_orphelins,
)


# =====================================================================
#  COUCHE BASE DE DONNÉES
# =====================================================================
class GestionnaireDB:
    def __init__(self, db_path="EauVive_prix.db"):
        """Initialise la connexion à la base de données"""
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._lock = threading.Lock()
        self.create_tables()

    # ------------------------------------------------------------------
    #  Connexion / création des tables
    # ------------------------------------------------------------------
    def _get_connection(self):
        """Obtient une connexion pour le thread courant"""
        with self._lock:
            if self.conn is None:
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self.cursor = self.conn.cursor()
            return self.conn, self.cursor

    def create_tables(self):
        """Crée les tables si elles n'existent pas"""
        conn, cursor = self._get_connection()

        # Table des catégories (avec hiérarchie)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS CATEGORIES (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL,
                parent_id INTEGER,
                FOREIGN KEY (parent_id) REFERENCES CATEGORIES(id),
                UNIQUE(nom, parent_id)
            )
        ''')

        # Table des produits - code_interne est la clé UNIQUE
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS PRODUITS (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_interne TEXT UNIQUE NOT NULL,
                ean TEXT,
                description TEXT NOT NULL,
                marque TEXT,
                volume TEXT,
                lien_fiche TEXT,
                caracteristique TEXT,
                url_img TEXT,
                categorie_id INTEGER,
                ean_valide INTEGER DEFAULT 0,
                date_validation DATE,
                FOREIGN KEY (categorie_id) REFERENCES CATEGORIES(id)
            )
        ''')

        # Table pour les conflits EAN
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS CONFLITS_EAN (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_interne_1 TEXT NOT NULL,
                code_interne_2 TEXT NOT NULL,
                ean TEXT NOT NULL,
                date_detection DATE NOT NULL,
                statut TEXT DEFAULT 'en_attente',
                commentaire TEXT,
                FOREIGN KEY (code_interne_1) REFERENCES PRODUITS(code_interne),
                FOREIGN KEY (code_interne_2) REFERENCES PRODUITS(code_interne)
            )
        ''')

        # Table des magasins
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS MAGASINS (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT UNIQUE NOT NULL,
                nomcsv TEXT,
                adresse TEXT,
                code_postal TEXT,
                ville TEXT,
                livraison_domicile INTEGER,
                retrait_magasin INTEGER,
                lien TEXT,
                sdv INTEGER
            )
        ''')

        # Table des relevés de prix
        #  -> prix, prix_old, prix_unit sont stockés en TEXTE (alphanumérique)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS RELEVES_PRIX (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                produit_id INTEGER NOT NULL,
                magasin_id INTEGER NOT NULL,
                date_releve DATE NOT NULL,
                prix TEXT NOT NULL,
                prix_old TEXT,
                prix_unit TEXT,
                FOREIGN KEY (produit_id) REFERENCES PRODUITS(id),
                FOREIGN KEY (magasin_id) REFERENCES MAGASINS(id),
                UNIQUE(produit_id, magasin_id, date_releve)
            )
        ''')

        conn.commit()

    # ------------------------------------------------------------------
    #  Utilitaires
    # ------------------------------------------------------------------
    def get_magasin_id(self, nom):
        """Récupère l'ID d'un magasin par son nom (nomcsv ou nom)"""
        conn, cursor = self._get_connection()
        cursor.execute(
            "SELECT id FROM MAGASINS WHERE nomcsv = ? OR nom = ?",
            (nom, nom)
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def get_categorie_id(self, nom):
        """Récupère l'ID d'une catégorie par son nom"""
        conn, cursor = self._get_connection()
        cursor.execute("SELECT id FROM CATEGORIES WHERE nom = ?", (nom,))
        result = cursor.fetchone()
        return result[0] if result else None

    def creer_categorie(self, nom, parent_id=None):
        """Crée une catégorie si elle n'existe pas et retourne son id"""
        conn, cursor = self._get_connection()
        cursor.execute(
            "INSERT OR IGNORE INTO CATEGORIES (nom, parent_id) VALUES (?, ?)",
            (nom, parent_id)
        )
        conn.commit()
        return self.get_categorie_id(nom)

    @staticmethod
    def _normaliser_prix(prix):
        """Normalise un prix ('10.75€', '1,25', 10.75) -> '10.75' (texte)."""
        if prix is None:
            return ''
        if isinstance(prix, (int, float)):
            return f"{prix:.2f}"
        s = str(prix).strip()
        # Retire tout sauf chiffres, point et virgule
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
        """Valide une chaîne YYMMDD et la convertit en YYYY-MM-DD.
        Retourne None si invalide."""
        if not re.fullmatch(r'\d{6}', date_str):
            return None
        try:
            yy = int(date_str[0:2])
            mm = int(date_str[2:4])
            dd = int(date_str[4:6])
            annee = 2000 + yy  # adapter si vos données remontent avant 2000
            datetime(annee, mm, dd)  # lève ValueError si date impossible
            return f"{annee:04d}-{mm:02d}-{dd:02d}"
        except (ValueError, IndexError):
            return None

    def extraire_metadonnees_fichier(self, fichier_path):
        """Extrait (magasin, date, catégorie) depuis un nom type :
            V5_<Magasin>_<YYMMDD>_<Catégorie>.json

        Le nom du magasin ET celui de la catégorie peuvent contenir des '_'.
        Le repère fiable est la date au format YYMMDD (6 chiffres,
        validée calendairement).

        Retourne (nom_magasin, date_releve, nom_categorie) ou
        (None, None, None) si le format est invalide.
        """
        nom_fichier = os.path.basename(fichier_path)
        if not nom_fichier.lower().endswith(".json"):
            return None, None, None

        # Retire l'extension .json puis le préfixe V5_
        nom_sans_extension = nom_fichier[:-5]
        if not nom_sans_extension.startswith("V5_"):
            return None, None, None

        reste = nom_sans_extension[3:]  # après "V5_"

        # On cherche le PREMIER segment _<YYMMDD>_ valide dans la chaîne.
        # Chaque segment candidat est un groupe de 6 chiffres délimité par
        # des underscores (ou début/fin de chaîne).
        #
        # Exemples :
        #   "Eau Vive_240315_Boissons"        -> date = "240315"
        #   "Bio_Coop_240315_Fruits_et_leg"   -> date = "240315"
        #   "Mon_Magasin_231201_Cat_Sub_Cat"  -> date = "231201"
        #
        # On utilise finditer pour repérer tous les _\d{6}(?=_|$) puis on
        # valide chaque candidat avant de retenir le premier valide.
        motif = re.compile(r'(?<=_)(\d{6})(?=_|$)')
        date_str = None
        date_debut = None  # index du début de la date dans `reste`

        for m in motif.finditer(reste):
            candidat = m.group(1)
            if self._valider_date_yymmdd(candidat) is not None:
                date_str = candidat
                date_debut = m.start(1)  # début des 6 chiffres
                break

        if date_str is None:
            return None, None, None

        date_releve = self._valider_date_yymmdd(date_str)

        # Magasin = tout ce qui précède la date (sans le '_' de séparation)
        nom_magasin = reste[:date_debut - 1].strip()

        # Catégorie = tout ce qui suit la date (sans le '_' de séparation)
        fin_date = date_debut + len(date_str)
        nom_categorie = reste[fin_date:].lstrip('_').strip()

        if not nom_magasin or not nom_categorie:
            return None, None, None

        return nom_magasin, date_releve, nom_categorie

    # ------------------------------------------------------------------
    #  Import produit / relevé (JSON)
    # ------------------------------------------------------------------
    def importer_produit_json(self, item, categorie_id=None):
        """Importe un produit depuis un dict JSON.

        Règles :
          - Si ref_id n'existe pas : insertion complète.
          - Si ref_id existe : mise à jour des champs vides uniquement.
          - Détection des conflits EAN.
        """
        try:
            code_interne = str(item.get('ref_id', '')).strip()
            if not code_interne:
                return False

            conn, cursor = self._get_connection()

            # Champs
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

            # Existence ?
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

            # Détection des conflits EAN
            self.detecter_conflits_ean(code_interne, ean)

            return True

        except Exception as e:
            print(f"❌ Erreur import produit {item.get('ref_id', '?')}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def importer_releve_prix_json(self, item, magasin_id, date_releve=None):
        """Importe un relevé de prix depuis un dict JSON.
        Les prix sont normalisés puis stockés sous forme TEXTE.
        """
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

            # Normalisation -> texte
            prix      = self._normaliser_prix(item.get('prix', ''))
            prix_old  = self._normaliser_prix(item.get('ancien_prix', ''))
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
        """Importe un fichier JSON complet.

        Format attendu :
          - Une liste de dicts, OU
          - Un dict contenant une clé 'produits' / 'products' / 'items' / 'data'
            pointant vers une liste, OU
          - Un dict unique (1 produit).
        """
        if not os.path.exists(fichier_path):
            msg = f"Fichier {fichier_path} non trouvé"
            if callback: callback(msg, 'error')
            return False

        try:
            # --- Métadonnées depuis le nom de fichier ---
            nom_magasin, date_releve, nom_famille = self.extraire_metadonnees_fichier(fichier_path)
            if nom_magasin is None or date_releve is None or nom_famille is None:
                msg = (f"Format de nom invalide (attendu : "
                       f"V5_<Magasin>_<YYMMDD>_<Catégorie>.json) : "
                       f"{os.path.basename(fichier_path)}")
                if callback: callback(msg, 'error')
                return False

            # --- Magasin ---
            if magasin_id is None:
                magasin_id = self.get_magasin_id(nom_magasin)
                if magasin_id is None:
                    # Création automatique du magasin si absent
                    magasin_id = self.creer_magasin(nom_magasin, nomcsv=nom_magasin)
                if magasin_id is None:
                    msg = f"Magasin '{nom_magasin}' introuvable."
                    if callback: callback(msg, 'error')
                    return False

            # --- Catégorie (famille) ---
            categorie_id = self.get_categorie_id(nom_famille)
            if categorie_id is None:
                categorie_id = self.creer_categorie(nom_famille)
            if categorie_id is None:
                msg = f"Catégorie '{nom_famille}' introuvable."
                if callback: callback(msg, 'error')
                return False

            # --- Lecture JSON ---
            with open(fichier_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Support : liste directe, dict enveloppant ou dict unique
            if isinstance(data, dict):
                for cle in ('produits', 'products', 'items', 'data'):
                    if cle in data and isinstance(data[cle], list):
                        data = data[cle]
                        break
                else:
                    data = [data]

            if not isinstance(data, list):
                msg = "Le JSON doit contenir une liste de produits."
                if callback: callback(msg, 'error')
                return False

            print(f"\n📁 Lecture du fichier: {os.path.basename(fichier_path)} "
                  f"({len(data)} entrées)")

            # >>> NOUVEAU : détection des références absentes <<<
            items_absents = detecter_references_absentes(data, self, callback=callback)
            if items_absents:
                # Log de synthèse (le détail a déjà été envoyé item par item)
                if callback:
                    callback(
                        f"{len(items_absents)} référence(s) absente(s) de la base "
                        f"seront ajoutée(s) (nouveaux produits).",
                        'info'
                    )
                # Génération d'un rapport texte à côté du JSON
                chemin_rapport = fichier_path + ".orphelins.txt"
                try:
                    generer_rapport_orphelins(items_absents, chemin_rapport)
                    if callback:
                        callback(f"Rapport orphelins écrit : {chemin_rapport}", 'info')
                except Exception as e:
                    if callback:
                        callback(f"Impossible d'écrire le rapport orphelins : {e}", 'warning')

            # >>> Suite du code d'import <<<
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
                        print(f"⚠️ Item {idx}: description vide "
                              f"pour ref_id {item.get('ref_id')}")

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
                   f"- {prix_importes} relevés de prix importés\n"
                   f"- {produits_sans_description} produits sans description\n"
                   f"- {ignores} entrées ignorées (sans ref_id)\n"
                   f"- {erreurs} erreurs")

            if callback: callback(msg, 'success')
            return True

        except json.JSONDecodeError as e:
            msg = f"JSON invalide : {e}"
            if callback: callback(msg, 'error')
            return False
        except Exception as e:
            msg = f"Erreur lors de l'importation : {e}"
            if callback: callback(msg, 'error')
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
            print(f"Erreur lors de la création du magasin: {e}")
            return None

    def detecter_conflits_ean(self, code_interne, ean):
        """Détecte si un EAN est déjà utilisé par un autre produit
        et remplit CONFLITS_EAN si nécessaire."""
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
            SELECT id, code_interne
            FROM PRODUITS
            WHERE ean = ? AND id != ?
        ''', (ean, produit_id_actuel))
        produits_conflits = cursor.fetchall()

        for produit_id_conflit, code_interne_conflit in produits_conflits:
            cursor.execute('''
                SELECT id FROM CONFLITS_EAN
                WHERE (code_interne_1 = ? AND code_interne_2 = ?)
                   OR (code_interne_1 = ? AND code_interne_2 = ?)
            ''', (
                code_interne, code_interne_conflit,
                code_interne_conflit, code_interne
            ))
            conflit_existant = cursor.fetchone()

            if not conflit_existant:
                date_detection = datetime.now().strftime('%Y-%m-%d')
                cursor.execute('''
                    INSERT INTO CONFLITS_EAN (
                        code_interne_1, code_interne_2, ean,
                        date_detection, statut
                    ) VALUES (?, ?, ?, ?, ?)
                ''', (
                    code_interne, code_interne_conflit, ean,
                    date_detection, 'en_attente'
                ))
                print(f"⚠️ Conflit EAN détecté entre {code_interne} "
                      f"et {code_interne_conflit} pour l'EAN {ean}")

        conn.commit()

    def get_statistiques(self):
        """Récupère les statistiques de la base"""
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
        """Vérifie les produits sans description"""
        conn, cursor = self._get_connection()
        cursor.execute("""
            SELECT code_interne, description, ean
            FROM PRODUITS
            WHERE description IS NULL OR description = ''
            LIMIT 10
        """)
        return cursor.fetchall()

    def fermer(self):
        """Ferme la connexion à la base de données"""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None


# =====================================================================
#  INTERFACE GRAPHIQUE
# =====================================================================
class ApplicationGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Gestionnaire de Catalogue Eau Vive")
        self.root.geometry("900x700")

        # Initialisation de la base de données
        self.db = GestionnaireDB("EauVive_prix.db")

        # Variables
        self.fichiers_selectionnes = []
        self.magasin_actuel = None
        self.importation_en_cours = False
        self.message_queue = queue.Queue()

        # Création du magasin par défaut
        self.magasin_id = self.db.creer_magasin(
            "Eau Vive",
            nomcsv="Eau Vive",
            adresse="Magasin bio",
            ville="France",
            livraison_domicile=1,
            retrait_magasin=1
        )

        # Interface
        self.creer_interface()
        self.mettre_a_jour_statistiques()

        # Démarrage du traitement des messages
        self.traiter_messages()

    # ------------------------------------------------------------------
    def creer_interface(self):
        # Barre de menu
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Fichier", menu=file_menu)
        file_menu.add_command(label="Importer des JSON", command=self.selectionner_fichiers)
        file_menu.add_separator()
        file_menu.add_command(
            label="Vérifier les produits sans description",
            command=self.verifier_sans_description
        )
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self.quitter)

        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)

        # Titre
        title = ttk.Label(
            main_frame,
            text="Gestionnaire de Catalogue Eau Vive",
            font=('Arial', 16, 'bold')
        )
        title.grid(row=0, column=0, columnspan=2, pady=10)

        # Statistiques
        stats_frame = ttk.LabelFrame(main_frame, text="Statistiques", padding="10")
        stats_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        self.stats_labels = {}
        stats = ['produits', 'releves', 'magasins', 'categories', 'sans_description']
        labels = ['Produits', 'Relevés de prix', 'Magasins', 'Catégories', 'Sans description']

        for i, (stat, label) in enumerate(zip(stats, labels)):
            ttk.Label(stats_frame, text=f"{label} :").grid(row=0, column=i * 2, padx=5)
            self.stats_labels[stat] = ttk.Label(stats_frame, text="0")
            self.stats_labels[stat].grid(row=0, column=i * 2 + 1, padx=5)

        # Importation
        import_frame = ttk.LabelFrame(main_frame, text="Importation JSON", padding="10")
        import_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        btn_frame = ttk.Frame(import_frame)
        btn_frame.grid(row=0, column=0, columnspan=3, pady=5)

        self.btn_selectionner = ttk.Button(
            btn_frame,
            text="📁 Sélectionner des fichiers JSON",
            command=self.selectionner_fichiers
        )
        self.btn_selectionner.pack(side=tk.LEFT, padx=5)

        self.btn_importer = ttk.Button(
            btn_frame,
            text="🚀 Importer les fichiers sélectionnés",
            command=self.importer_fichiers
        )
        self.btn_importer.pack(side=tk.LEFT, padx=5)

        self.btn_vider = ttk.Button(
            btn_frame,
            text="🗑️ Vider la liste",
            command=self.vider_liste
        )
        self.btn_vider.pack(side=tk.LEFT, padx=5)

        # Barre de progression
        self.progress_bar = ttk.Progressbar(import_frame, mode='indeterminate')
        self.progress_bar.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        # Liste des fichiers
        ttk.Label(import_frame, text="Fichiers sélectionnés :").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )

        list_frame = ttk.Frame(import_frame)
        list_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        list_frame.columnconfigure(0, weight=1)

        self.liste_fichiers = tk.Listbox(list_frame, height=5, width=80)
        self.liste_fichiers.grid(row=0, column=0, sticky=(tk.W, tk.E))

        scrollbar = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.liste_fichiers.yview
        )
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.liste_fichiers.config(yscrollcommand=scrollbar.set)

        # Journal
        log_frame = ttk.LabelFrame(main_frame, text="📋 Journal", padding="10")
        log_frame.grid(
            row=3, column=0, columnspan=2,
            sticky=(tk.W, tk.E, tk.N, tk.S), pady=10
        )
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.grid(row=1, column=0, pady=5)

        ttk.Button(
            log_btn_frame, text="📄 Exporter le journal",
            command=self.exporter_log
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            log_btn_frame, text="🗑️ Effacer le journal",
            command=self.effacer_log
        ).pack(side=tk.LEFT, padx=5)

    # ------------------------------------------------------------------
    #  Journal / log
    # ------------------------------------------------------------------
    def log(self, message, type_message='info'):
        self.message_queue.put((message, type_message))

    def traiter_messages(self):
        try:
            while not self.message_queue.empty():
                message, type_message = self.message_queue.get_nowait()
                self._log_immediat(message, type_message)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.traiter_messages)

    def _log_immediat(self, message, type_message='info'):
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = {
            'info': 'ℹ️',
            'success': '✅',
            'error': '❌',
            'warning': '⚠️'
        }.get(type_message, 'ℹ️')

        self.log_text.tag_config('info', foreground='black')
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')
        self.log_text.tag_config('warning', foreground='orange')

        self.log_text.insert(tk.END, f"[{timestamp}] {prefix} {message}\n", type_message)
        self.log_text.see(tk.END)

    def exporter_log(self):
        filename = filedialog.asksaveasfilename(
            title="Exporter le journal",
            defaultextension=".txt",
            filetypes=[("Fichiers texte", "*.txt"), ("Tous les fichiers", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, tk.END))
                messagebox.showinfo("Succès", f"Journal exporté vers {filename}")
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur lors de l'export : {e}")

    def effacer_log(self):
        if messagebox.askyesno("Effacer le journal",
                               "Voulez-vous vraiment effacer le journal ?"):
            self.log_text.delete(1.0, tk.END)
            self.log("Journal effacé", 'info')

    # ------------------------------------------------------------------
    def mettre_a_jour_statistiques(self):
        stats = self.db.get_statistiques()
        for key, value in stats.items():
            if key in self.stats_labels:
                self.stats_labels[key].config(text=str(value))

    # ------------------------------------------------------------------
    def selectionner_fichiers(self):
        fichiers = filedialog.askopenfilenames(
            title="Sélectionner les fichiers JSON à importer",
            filetypes=[("Fichiers JSON", "*.json"), ("Tous les fichiers", "*.*")]
        )
        if fichiers:
            for fichier in fichiers:
                if fichier not in self.fichiers_selectionnes:
                    self.fichiers_selectionnes.append(fichier)
                    self.liste_fichiers.insert(tk.END, os.path.basename(fichier))
            self.log(f"{len(fichiers)} fichier(s) ajouté(s) à la liste", 'info')

    def vider_liste(self):
        self.fichiers_selectionnes.clear()
        self.liste_fichiers.delete(0, tk.END)
        self.log("Liste des fichiers vidée", 'info')

    def verifier_sans_description(self):
        produits = self.db.verifier_produits_sans_description()
        if not produits:
            messagebox.showinfo("Information", "Tous les produits ont une description.")
            return

        fenetre = tk.Toplevel(self.root)
        fenetre.title("Produits sans description")
        fenetre.geometry("600x400")

        frame = ttk.Frame(fenetre, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=f"{len(produits)} produit(s) sans description :",
            font=('Arial', 10, 'bold')
        ).pack(pady=5)

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        for produit in produits:
            listbox.insert(
                tk.END,
                f"Code: {produit[0]} | EAN: {produit[2] or 'N/A'}"
            )

        ttk.Button(frame, text="Fermer", command=fenetre.destroy).pack(pady=10)

    # ------------------------------------------------------------------
    def importer_fichiers(self):
        if not self.fichiers_selectionnes:
            messagebox.showwarning(
                "Aucun fichier",
                "Veuillez sélectionner des fichiers à importer."
            )
            return

        if self.importation_en_cours:
            messagebox.showwarning(
                "Importation en cours",
                "Une importation est déjà en cours."
            )
            return

        self.importation_en_cours = True
        self.btn_selectionner.config(state='disabled')
        self.btn_importer.config(state='disabled')
        self.btn_vider.config(state='disabled')
        self.progress_bar.start()

        def importer():
            try:
                fichiers_erreur = []
                fichiers_a_importer = self.fichiers_selectionnes.copy()
                total_fichiers = len(fichiers_a_importer)

                for idx, fichier in enumerate(fichiers_a_importer):
                    nom_fichier = os.path.basename(fichier)
                    self.log(
                        f"[{idx + 1}/{total_fichiers}] Importation de {nom_fichier}...",
                        'info'
                    )

                    def callback(message, type_message, nf=nom_fichier):
                        self.log(f"{nf}: {message}", type_message)

                    # magasin_id=None : extrait automatiquement du nom de fichier
                    success = self.db.importer_fichier_json(fichier, callback=callback)

                    if not success:
                        fichiers_erreur.append(nom_fichier)

                self.root.after(0, self.mettre_a_jour_statistiques)

                if fichiers_erreur:
                    self.log(
                        f"⚠️ {len(fichiers_erreur)} fichier(s) ont rencontré des erreurs",
                        'warning'
                    )
                else:
                    self.log("✅ Tous les fichiers ont été importés avec succès !", 'success')

                self.root.after(0, lambda: messagebox.showinfo(
                    "Succès",
                    f"L'importation est terminée.\n"
                    f"{len(fichiers_erreur)} fichier(s) en erreur."
                ))

            except Exception as e:
                self.log(f"Erreur fatale lors de l'importation : {str(e)}", 'error')
                self.root.after(0, lambda: messagebox.showerror(
                    "Erreur", f"Une erreur est survenue : {str(e)}"
                ))
            finally:
                self.root.after(0, self.fin_importation)

        thread = threading.Thread(target=importer)
        thread.daemon = True
        thread.start()

    def fin_importation(self):
        self.importation_en_cours = False
        self.btn_selectionner.config(state='normal')
        self.btn_importer.config(state='normal')
        self.btn_vider.config(state='normal')
        self.progress_bar.stop()

    def quitter(self):
        if self.importation_en_cours:
            if not messagebox.askokcancel(
                "Quitter",
                "Une importation est en cours. Voulez-vous vraiment quitter ?"
            ):
                return

        if messagebox.askokcancel("Quitter", "Voulez-vous vraiment quitter ?"):
            self.db.fermer()
            self.root.quit()


# =====================================================================
#  INTERFACES
# =====================================================================
def interface_cli():
    """Interface en ligne de commande"""
    parser = argparse.ArgumentParser(description="Gestionnaire de catalogue Eau Vive")
    parser.add_argument("--import", dest="fichiers", nargs="+",
                        help="Fichiers JSON à importer")
    parser.add_argument("--magasin", default="Eau Vive", help="Nom du magasin")
    parser.add_argument("--stats", action="store_true", help="Afficher les statistiques")
    parser.add_argument("--db", default="EauVive_prix.db",
                        help="Chemin de la base de données")

    args = parser.parse_args()

    db = GestionnaireDB(args.db)

    try:
        # Créer (ou récupérer) le magasin par défaut
        db.creer_magasin(args.magasin, nomcsv=args.magasin)

        if args.fichiers:
            print("\n=== Importation des fichiers JSON ===")
            for fichier in args.fichiers:
                print(f"\nImportation de {fichier}...")
                # magasin_id=None : extraction auto depuis le nom de fichier
                db.importer_fichier_json(fichier)

        if args.stats:
            stats = db.get_statistiques()
            print("\n=== Statistiques de la base de données ===")
            print(f"Produits : {stats['produits']}")
            print(f"Relevés de prix : {stats['releves']}")
            print(f"Magasins : {stats['magasins']}")
            print(f"Catégories : {stats['categories']}")
            print(f"Sans description : {stats['sans_description']}")
            print("==========================================")

    finally:
        db.fermer()


def interface_gui():
    """Interface graphique Tkinter"""
    root = tk.Tk()
    app = ApplicationGUI(root)
    root.mainloop()


def main():
    """Fonction principale"""
    if len(sys.argv) > 1:
        interface_cli()
    else:
        interface_gui()


if __name__ == "__main__":
    main()