import sqlite3
import csv
import os
from datetime import datetime
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import sys
import argparse
import queue
import re


class GestionnaireDB:
    def __init__(self, db_path="EauVive_prix.db"):
        """Initialise la connexion à la base de données"""
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._lock = threading.Lock()
        self.create_tables()

    def get_magasin_id(self, nom):
        """Récupère l'ID d'un magasin par son nom"""
        conn, cursor = self._get_connection()
        cursor.execute("SELECT id FROM MAGASINS WHERE nomcsv = ?", (nom,))
        result = cursor.fetchone()
        return result[0] if result else None

    def get_categorie_id(self, nom):
        """Récupère l'ID d'une catégorie par son nom"""
        conn, cursor = self._get_connection()
        cursor.execute("SELECT id FROM CATEGORIES WHERE nom = ?", (nom,))
        result = cursor.fetchone()
        return result[0] if result else None

    def extraire_metadonnees_fichier(self, fichier_path):
        """Extrait le nom du magasin, la date et la catégorie depuis le nom du fichier"""
        nom_fichier = os.path.basename(fichier_path)
        if not nom_fichier.startswith("GRAB-"):
            return None, None, None  # Format invalide

        # Supprimer l'extension .csv
        nom_sans_extension = nom_fichier.replace(".csv", "")

        # Diviser le nom en parties
        parts = nom_sans_extension.split("-")

        # Il faut au minimum 4 parties : GRAB, Magasin, Date, Categorie
        if len(parts) < 4:
            return None, None, None  # Format invalide

        # La catégorie est toujours le dernier élément
        nom_categorie = parts[-1]

        # La date est toujours l'avant-dernier élément
        date_str = parts[-2]

        # Le magasin est tout ce qui se trouve entre "GRAB" et la date.
        # On prend de l'index 1 jusqu'à l'avant-dernier (exclu) et on recolle avec des tirets.
        nom_magasin = "-".join(parts[1:-2])

        # Convertir la date en format YYYY-MM-DD
        try:
            date_releve = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except:
            date_releve = None

        return nom_magasin, date_releve, nom_categorie


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

        # Table pour les conflits EAN à résoudre manuellement
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

    def parse_tags(self, tags_str):
        """Parse les tags du CSV et les convertit en une chaîne de caractères"""
        if not tags_str or tags_str == '[]':
            return ''

        try:
            # Nettoyer la chaîne
            tags_str = tags_str.strip()

            # Remplacer les guillemets simples par des doubles pour JSON
            tags_str = tags_str.replace("'", '"')

            # Essayer de parser comme JSON
            try:
                tags = json.loads(tags_str)
            except:
                # Si JSON échoue, essayer avec eval
                tags = eval(tags_str)

            parsed_tags = []
            if isinstance(tags, list):
                for tag in tags:
                    if isinstance(tag, dict):
                        parsed_tags.append(tag.get('text', ''))
                    else:
                        parsed_tags.append(str(tag))
            return '; '.join(parsed_tags)
        except Exception as e:
            print(f"Erreur lors du parsing des tags: {e}")
            return str(tags_str)

    def importer_produit(self, row, categorie_id=None):
        """Importe un produit depuis une ligne CSV en respectant les règles :
        - Si ref_id n'existe pas : insère tout ce qui est possible.
        - Si ref_id existe : met à jour uniquement les champs vides.
        - Détecte les conflits EAN et remplit CONFLITS_EAN.
        """
        try:
            code_interne = row.get('ref_id', '').strip()
            if not code_interne:
                return False

            conn, cursor = self._get_connection()

            # Récupérer les valeurs du CSV
            description = row.get('name', '').strip()
            if not description:
                description = row.get('off_name', '').strip()
            if not description:
                description = f"Produit {code_interne}"
                print(f"⚠️ Description manquante pour le produit {code_interne}")

            ean = row.get('ean', '').strip()
            if not ean:
                ean = row.get('ean_api', '').strip()

            marque = None  # Non utilisé
            volume = row.get('volume', '').strip()
            lien_fiche = row.get('url', '').strip()
            if lien_fiche and not lien_fiche.startswith('http'):
                lien_fiche = f"https://eau-vive.com{lien_fiche}"

            url_img = row.get('img_eauvive_url', '').strip()
            if not url_img:
                url_img = row.get('img_eauvive_alt', '').strip()

            tags_str = row.get('tags', '[]')
            caracteristique = self.parse_tags(tags_str)

            # Vérifier si le produit existe déjà
            cursor.execute("SELECT * FROM PRODUITS WHERE code_interne = ?", (code_interne,))
            produit_existant = cursor.fetchone()

            if produit_existant:
                cursor.execute('''
                    UPDATE PRODUITS SET
                        ean = COALESCE(NULLIF(?, ''), ean),
                        description = COALESCE(NULLIF(?, ''), description),
                        volume = COALESCE(NULLIF(?, ''), volume),
                        lien_fiche = COALESCE(NULLIF(?, ''), lien_fiche),
                        caracteristique = COALESCE(NULLIF(?, ''), caracteristique),
                        url_img = COALESCE(NULLIF(?, ''), url_img),
                        categorie_id = CASE
                            WHEN categorie_id IS NULL OR categorie_id = 10 THEN COALESCE(?, categorie_id)
                            ELSE categorie_id
                        END
                    WHERE code_interne = ?
                ''', (ean, description, volume, lien_fiche, caracteristique, url_img, categorie_id, code_interne))
            else:
                # Produit n'existe pas : insérer toutes les informations
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

            # Détecter les conflits EAN
            self.detecter_conflits_ean(code_interne, ean)

            return True

        except Exception as e:
            print(f"❌ Erreur lors de l'import du produit {row.get('ref_id', 'inconnu')}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def importer_releve_prix(self, row, magasin_id, date_releve=None):
        """Importe un relevé de prix depuis une ligne CSV avec une date personnalisée"""
        try:
            code_interne = row.get('ref_id', '').strip()
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

            prix = row.get('price', '').strip()
            prix_old = row.get('price_old', '').strip()
            prix_unit = row.get('price_unit', '').strip()

            # Utiliser la date fournie ou la date du jour
            if date_releve is None:
                date_releve = datetime.now().strftime('%Y-%m-%d')

            cursor.execute('''
                INSERT OR IGNORE INTO RELEVES_PRIX (
                    produit_id, magasin_id, date_releve,
                    prix, prix_old, prix_unit
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                produit_id, magasin_id, date_releve,
                prix, prix_old, prix_unit
            ))

            return True

        except Exception as e:
            print(f"❌ Erreur lors de l'import du relevé pour {row.get('ref_id', 'inconnu')}: {e}")
            return False

    def importer_fichier_csv(self, fichier_path, magasin_id=None, callback=None):
        """Importe un fichier CSV avec extraction des métadonnées depuis le nom du fichier"""
        if not os.path.exists(fichier_path):
            message = f"Fichier {fichier_path} non trouvé"
            if callback:
                callback(message, 'error')
            return False

        try:
            # Extraire les métadonnées du nom de fichier
            nom_magasin, date_releve, nom_categorie = self.extraire_metadonnees_fichier(fichier_path)

            if nom_magasin is None or date_releve is None or nom_categorie is None:
                message = f"Format de nom de fichier invalide : {os.path.basename(fichier_path)}"
                if callback:
                    callback(message, 'error')
                return False

            # Récupérer les IDs
            if magasin_id is None:
                magasin_id = self.get_magasin_id(nom_magasin)
                if magasin_id is None:
                    message = f"Magasin '{nom_magasin}' non trouvé dans la base."
                    if callback:
                        callback(message, 'error')
                    return False

            categorie_id = self.get_categorie_id(nom_categorie)
            if categorie_id is None:
                message = f"Catégorie '{nom_categorie}' non trouvée dans la base."
                if callback:
                    callback(message, 'error')
                return False

            produits_importes = 0
            prix_importes = 0
            erreurs = 0
            produits_sans_description = 0
            lignes_ignorees = 0

            print(f"\n📁 Lecture du fichier: {os.path.basename(fichier_path)}")

            with open(fichier_path, 'r', encoding='utf-8-sig') as f:
                header_line = f.readline().strip()
                header_line = re.sub(r'\s*;\s*', ';', header_line)
                headers = [h.strip() for h in header_line.split(';')]

                print(f"📋 En-têtes détectés: {headers}")

                if 'name' not in headers and 'ref_id' not in headers:
                    message = "Le fichier ne contient pas les colonnes requises (name et ref_id)"
                    if callback:
                        callback(message, 'error')
                    return False

                field_mapping = {}
                for i, h in enumerate(headers):
                    h_clean = h.lower().strip()
                    if h_clean == 'name':
                        field_mapping['name'] = i
                    elif h_clean == 'ref_id':
                        field_mapping['ref_id'] = i
                    elif h_clean == 'url':
                        field_mapping['url'] = i
                    elif h_clean == 'img_eauvive_url':
                        field_mapping['img_eauvive_url'] = i
                    elif h_clean == 'img_eauvive_alt':
                        field_mapping['img_eauvive_alt'] = i
                    elif h_clean == 'ean':
                        field_mapping['ean'] = i
                    elif h_clean == 'ean_api':
                        field_mapping['ean_api'] = i
                    elif h_clean == 'volume':
                        field_mapping['volume'] = i
                    elif h_clean == 'price':
                        field_mapping['price'] = i
                    elif h_clean == 'price_old':
                        field_mapping['price_old'] = i
                    elif h_clean == 'price_unit':
                        field_mapping['price_unit'] = i
                    elif h_clean == 'tags':
                        field_mapping['tags'] = i
                    elif h_clean == 'off_name':
                        field_mapping['off_name'] = i

                print(f"🔍 Mapping des colonnes: {field_mapping}")

                if 'ref_id' not in field_mapping or 'name' not in field_mapping:
                    message = f"Colonnes ref_id ou name non trouvées. En-têtes: {headers}"
                    if callback:
                        callback(message, 'error')
                    return False

                for line_num, line in enumerate(f, start=2):
                    try:
                        line = line.strip()
                        if not line:
                            continue

                        line = re.sub(r'\s*;\s*', ';', line)
                        values = line.split(';')

                        row = {}
                        for field, idx in field_mapping.items():
                            if idx < len(values):
                                row[field] = values[idx].strip()
                            else:
                                row[field] = ''

                        if not row.get('ref_id'):
                            lignes_ignorees += 1
                            continue

                        if not row.get('name'):
                            produits_sans_description += 1
                            print(f"⚠️ Ligne {line_num}: name vide pour ref_id {row.get('ref_id')}")

                        # Importer le produit avec la catégorie
                        if self.importer_produit(row, categorie_id):
                            produits_importes += 1
                        else:
                            erreurs += 1
                            continue

                        # Importer le relevé de prix avec la date et le magasin
                        if self.importer_releve_prix(row, magasin_id, date_releve):
                            prix_importes += 1

                    except Exception as e:
                        erreurs += 1
                        print(f"❌ Erreur ligne {line_num}: {e}")
                        continue

            conn, _ = self._get_connection()
            conn.commit()

            message = (f"Importation terminée :\n"
                       f"- {produits_importes} produits importés/mis à jour\n"
                       f"- {prix_importes} relevés de prix importés\n"
                       f"- {produits_sans_description} produits sans description\n"
                       f"- {lignes_ignorees} lignes ignorées (sans ref_id)\n"
                       f"- {erreurs} erreurs")

            if callback:
                callback(message, 'success')
            return True

        except Exception as e:
            message = f"Erreur lors de l'importation : {str(e)}"
            if callback:
                callback(message, 'error')
            import traceback
            traceback.print_exc()
            return False

    def creer_magasin(self, nom, **kwargs):
        """Crée un magasin"""
        try:
            conn, cursor = self._get_connection()

            cursor.execute('''
                INSERT OR IGNORE INTO MAGASINS (
                    nom, adresse, code_postal, ville,
                    livraison_domicile, retrait_magasin, lien, sdv
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                nom,
                kwargs.get('adresse', ''),
                kwargs.get('code_postal', ''),
                kwargs.get('ville', ''),
                kwargs.get('livraison_domicile', 0),
                kwargs.get('retrait_magasin', 0),
                kwargs.get('lien', ''),
                kwargs.get('sdv', 0)
            ))
            conn.commit()

            cursor.execute("SELECT id FROM MAGASINS WHERE nom = ?", (nom,))
            result = cursor.fetchone()
            return result[0] if result else None

        except Exception as e:
            print(f"Erreur lors de la création du magasin: {e}")
            return None

    def detecter_conflits_ean(self, code_interne, ean):
        """Détecte si un EAN est déjà utilisé par un autre produit et remplit CONFLITS_EAN si nécessaire."""
        if not ean:
            return  # Pas d'EAN à vérifier

        conn, cursor = self._get_connection()

        # Récupérer l'ID du produit actuel
        cursor.execute("SELECT id FROM PRODUITS WHERE code_interne = ?", (code_interne,))
        produit_actuel = cursor.fetchone()
        if not produit_actuel:
            return  # Produit non trouvé (ne devrait pas arriver)

        produit_id_actuel = produit_actuel[0]

        # Chercher d'autres produits avec le même EAN
        cursor.execute('''
            SELECT id, code_interne
            FROM PRODUITS
            WHERE ean = ? AND id != ?
        ''', (ean, produit_id_actuel))

        produits_conflits = cursor.fetchall()

        for produit_conflit in produits_conflits:
            produit_id_conflit, code_interne_conflit = produit_conflit

            # Vérifier si le conflit est déjà enregistré
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
                # Enregistrer le conflit
                date_detection = datetime.now().strftime('%Y-%m-%d')
                cursor.execute('''
                    INSERT INTO CONFLITS_EAN (
                        code_interne_1, code_interne_2, ean, date_detection, statut
                    ) VALUES (?, ?, ?, ?, ?)
                ''', (
                    code_interne, code_interne_conflit, ean, date_detection, 'en_attente'
                ))
                print(f"⚠️ Conflit EAN détecté entre {code_interne} et {code_interne_conflit} pour l'EAN {ean}")

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

        cursor.execute("SELECT COUNT(*) FROM PRODUITS WHERE description IS NULL OR description = ''")
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
            adresse="Magasin bio",
            ville="France",
            livraison_domicile=1,
            retrait_magasin=1
        )

        # Interface
        self.creer_interface()
        self.mettre_a_jour_statistiques()

        # Démarrer le traitement des messages
        self.traiter_messages()

    def creer_interface(self):
        # Barre de menu
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Fichier", menu=file_menu)
        file_menu.add_command(label="Importer des CSV", command=self.importer_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Vérifier les produits sans description", command=self.verifier_sans_description)
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self.quitter)

        # Frame principal avec scroll
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configuration du redimensionnement
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)

        # Titre
        title = ttk.Label(main_frame, text="Gestionnaire de Catalogue Eau Vive", font=('Arial', 16, 'bold'))
        title.grid(row=0, column=0, columnspan=2, pady=10)

        # Section statistiques
        stats_frame = ttk.LabelFrame(main_frame, text="Statistiques", padding="10")
        stats_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        self.stats_labels = {}
        stats = ['produits', 'releves', 'magasins', 'categories', 'sans_description']
        labels = ['Produits', 'Relevés de prix', 'Magasins', 'Catégories', 'Sans description']

        for i, (stat, label) in enumerate(zip(stats, labels)):
            ttk.Label(stats_frame, text=f"{label} :").grid(row=0, column=i * 2, padx=5)
            self.stats_labels[stat] = ttk.Label(stats_frame, text="0")
            self.stats_labels[stat].grid(row=0, column=i * 2 + 1, padx=5)

        # Section importation
        import_frame = ttk.LabelFrame(main_frame, text="Importation CSV", padding="10")
        import_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        # Boutons d'import
        btn_frame = ttk.Frame(import_frame)
        btn_frame.grid(row=0, column=0, columnspan=3, pady=5)

        self.btn_selectionner = ttk.Button(btn_frame, text="📁 Sélectionner des fichiers CSV",
                                           command=self.selectionner_fichiers)
        self.btn_selectionner.pack(side=tk.LEFT, padx=5)

        self.btn_importer = ttk.Button(btn_frame, text="🚀 Importer les fichiers sélectionnés",
                                       command=self.importer_fichiers)
        self.btn_importer.pack(side=tk.LEFT, padx=5)

        self.btn_vider = ttk.Button(btn_frame, text="🗑️ Vider la liste",
                                    command=self.vider_liste)
        self.btn_vider.pack(side=tk.LEFT, padx=5)

        # Barre de progression
        self.progress_bar = ttk.Progressbar(import_frame, mode='indeterminate')
        self.progress_bar.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        # Liste des fichiers
        ttk.Label(import_frame, text="Fichiers sélectionnés :").grid(row=2, column=0, sticky=tk.W, pady=5)

        list_frame = ttk.Frame(import_frame)
        list_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        list_frame.columnconfigure(0, weight=1)

        self.liste_fichiers = tk.Listbox(list_frame, height=5, width=80)
        self.liste_fichiers.grid(row=0, column=0, sticky=(tk.W, tk.E))

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.liste_fichiers.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.liste_fichiers.config(yscrollcommand=scrollbar.set)

        # Log
        log_frame = ttk.LabelFrame(main_frame, text="📋 Journal", padding="10")
        log_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Boutons du journal
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.grid(row=1, column=0, pady=5)

        ttk.Button(log_btn_frame, text="📄 Exporter le journal",
                   command=self.exporter_log).pack(side=tk.LEFT, padx=5)

        ttk.Button(log_btn_frame, text="🗑️ Effacer le journal",
                   command=self.effacer_log).pack(side=tk.LEFT, padx=5)

    def log(self, message, type_message='info'):
        """Ajoute un message au journal via la queue"""
        self.message_queue.put((message, type_message))

    def traiter_messages(self):
        """Traite les messages dans la queue"""
        try:
            while not self.message_queue.empty():
                message, type_message = self.message_queue.get_nowait()
                self._log_immediat(message, type_message)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.traiter_messages)

    def _log_immediat(self, message, type_message='info'):
        """Affiche immédiatement le message dans le journal"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = {
            'info': 'ℹ️',
            'success': '✅',
            'error': '❌',
            'warning': '⚠️'
        }.get(type_message, 'ℹ️')

        # Couleurs pour le log
        tags = {
            'info': 'black',
            'success': 'green',
            'error': 'red',
            'warning': 'orange'
        }

        self.log_text.insert(tk.END, f"[{timestamp}] {prefix} {message}\n", type_message)
        self.log_text.tag_config('info', foreground='black')
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')
        self.log_text.tag_config('warning', foreground='orange')
        self.log_text.see(tk.END)

    def exporter_log(self):
        """Exporte le journal dans un fichier"""
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
        """Efface le contenu du journal"""
        if messagebox.askyesno("Effacer le journal", "Voulez-vous vraiment effacer le journal ?"):
            self.log_text.delete(1.0, tk.END)
            self.log("Journal effacé", 'info')

    def mettre_a_jour_statistiques(self):
        """Met à jour les statistiques affichées"""
        stats = self.db.get_statistiques()
        for key, value in stats.items():
            if key in self.stats_labels:
                self.stats_labels[key].config(text=str(value))

    def selectionner_fichiers(self):
        """Ouvre une boîte de dialogue pour sélectionner des fichiers CSV"""
        fichiers = filedialog.askopenfilenames(
            title="Sélectionner les fichiers CSV à importer",
            filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")]
        )

        if fichiers:
            for fichier in fichiers:
                if fichier not in self.fichiers_selectionnes:
                    self.fichiers_selectionnes.append(fichier)
                    self.liste_fichiers.insert(tk.END, os.path.basename(fichier))
            self.log(f"{len(fichiers)} fichier(s) ajouté(s) à la liste", 'info')

    def vider_liste(self):
        """Vide la liste des fichiers sélectionnés"""
        self.fichiers_selectionnes.clear()
        self.liste_fichiers.delete(0, tk.END)
        self.log("Liste des fichiers vidée", 'info')

    def verifier_sans_description(self):
        """Vérifie les produits sans description"""
        produits = self.db.verifier_produits_sans_description()

        if not produits:
            messagebox.showinfo("Information", "Tous les produits ont une description.")
            return

        # Créer une fenêtre pour afficher les produits sans description
        fenetre = tk.Toplevel(self.root)
        fenetre.title("Produits sans description")
        fenetre.geometry("600x400")

        frame = ttk.Frame(fenetre, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=f"{len(produits)} produit(s) sans description :", font=('Arial', 10, 'bold')).pack(pady=5)

        # Liste avec scroll
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        for produit in produits:
            listbox.insert(tk.END, f"Code: {produit[0]} | EAN: {produit[2] or 'N/A'}")

        ttk.Button(frame, text="Fermer", command=fenetre.destroy).pack(pady=10)

    def importer_fichiers(self):
        """Importe les fichiers sélectionnés"""
        if not self.fichiers_selectionnes:
            messagebox.showwarning("Aucun fichier", "Veuillez sélectionner des fichiers à importer.")
            return

        if self.importation_en_cours:
            messagebox.showwarning("Importation en cours", "Une importation est déjà en cours.")
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
                    self.log(f"[{idx + 1}/{total_fichiers}] Importation de {nom_fichier}...", 'info')

                    def callback(message, type_message):
                        self.log(f"{nom_fichier}: {message}", type_message)

                    # Ne pas passer magasin_id, il sera extrait du nom du fichier
                    success = self.db.importer_fichier_csv(fichier, callback=callback)

                    if not success:
                        fichiers_erreur.append(nom_fichier)

                self.root.after(0, self.mettre_a_jour_statistiques)

                if fichiers_erreur:
                    self.log(f"⚠️ {len(fichiers_erreur)} fichier(s) ont rencontré des erreurs", 'warning')
                else:
                    self.log("✅ Tous les fichiers ont été importés avec succès !", 'success')

                messagebox.showinfo("Succès",
                                    f"L'importation est terminée.\n{len(fichiers_erreur)} fichier(s) en erreur.")

            except Exception as e:
                self.log(f"Erreur fatale lors de l'importation : {str(e)}", 'error')
                messagebox.showerror("Erreur", f"Une erreur est survenue : {str(e)}")
            finally:
                self.root.after(0, self.fin_importation)

        thread = threading.Thread(target=importer)
        thread.daemon = True
        thread.start()

    def fin_importation(self):
        """Réactive les boutons après l'importation"""
        self.importation_en_cours = False
        self.btn_selectionner.config(state='normal')
        self.btn_importer.config(state='normal')
        self.btn_vider.config(state='normal')
        self.progress_bar.stop()

    def importer_csv(self):
        """Ouvre la boîte de dialogue d'import depuis le menu"""
        self.selectionner_fichiers()

    def quitter(self):
        """Ferme l'application"""
        if self.importation_en_cours:
            if not messagebox.askokcancel("Quitter", "Une importation est en cours. Voulez-vous vraiment quitter ?"):
                return

        if messagebox.askokcancel("Quitter", "Voulez-vous vraiment quitter ?"):
            self.db.fermer()
            self.root.quit()


def interface_cli():
    """Interface en ligne de commande"""
    parser = argparse.ArgumentParser(description="Gestionnaire de catalogue Eau Vive")
    parser.add_argument("--import", dest="fichiers", nargs="+", help="Fichiers CSV à importer")
    parser.add_argument("--magasin", default="Eau Vive", help="Nom du magasin")
    parser.add_argument("--stats", action="store_true", help="Afficher les statistiques")
    parser.add_argument("--db", default="EauVive_prix.db", help="Chemin de la base de données")

    args = parser.parse_args()

    db = GestionnaireDB(args.db)

    try:
        magasin_id = db.creer_magasin(args.magasin)

        if args.fichiers:
            print("\n=== Importation des fichiers CSV ===")
            for fichier in args.fichiers:
                print(f"\nImportation de {fichier}...")
                db.importer_fichier_csv(fichier, magasin_id)

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