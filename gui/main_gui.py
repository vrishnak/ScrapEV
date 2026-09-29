import os
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from utils.scraper_utils import ScraperV6, charger_json
from utils.ev_connection import get_connected_driver
from BDC_EauVive_V3 import GestionnaireDB

CONFIG_FILE = os.path.join("config", "config_v6.json")

class ScrapApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Scraper V6 - EauVive (GUI)")
        self.root.geometry("900x700")

        # Configuration par défaut
        self.config = {
            "magasins_json": os.path.join("EAUVIVE_Liste", "EauVive_Liste_300.json"),
            "familles_json": os.path.join("EAUVIVE_Liste", "EauVive_URL_Pates.json"),
            "headless": True,
            "save_json": True,
            "save_excel": False,
            "dir_json": "DATA_EV/JSON",
            "dir_excel": "DATA_EV/XLSX",
            "db_file": "EauVive_prix.db"
        }
        self.load_config()

        self.magasins_data = []
        self.familles_data = []
        
        self.create_widgets()
        self.refresh_lists()

    def load_config(self):
        """Charge la configuration depuis un fichier JSON."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.config.update(json.load(f))
            except:
                pass

    def save_config(self):
        """Sauvegarde la configuration dans un fichier JSON."""
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de sauvegarder la config: {e}")

    def create_widgets(self):
        """Crée l'ensemble des éléments de l'interface."""
        # Création du Notebook (système d'onglets)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # ---------------------------------------------------------
        # Onglet Principal (Scraping)
        # ---------------------------------------------------------
        self.tab_main = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_main, text="🚀 Scraping")
        self.create_main_tab()

        # ---------------------------------------------------------
        # Onglet Base de Données
        # ---------------------------------------------------------
        #self.tab_db = ttk.Frame(self.notebook)
        #self.notebook.add(self.tab_db, text="🗄️ Base de Données")
        #self.create_db_tab()

        # ---------------------------------------------------------
        # Onglet Paramètres
        # ---------------------------------------------------------
        self.tab_settings = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_settings, text="⚙️ Paramètres")
        self.create_settings_tab()

    def create_main_tab(self):
        """Génère le contenu de l'onglet Principal."""
        # Zone pour les listes
        lists_frame = ttk.Frame(self.tab_main)
        lists_frame.pack(fill='both', expand=True, padx=5, pady=5)

        # 1. Liste des magasins
        magasins_frame = ttk.LabelFrame(lists_frame, text="🏪 Magasins")
        magasins_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        self.listbox_magasins = tk.Listbox(magasins_frame, selectmode=tk.MULTIPLE, exportselection=False)
        self.listbox_magasins.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scrollbar_mag = ttk.Scrollbar(magasins_frame, orient="vertical", command=self.listbox_magasins.yview)
        scrollbar_mag.pack(side='right', fill='y')
        self.listbox_magasins.config(yscrollcommand=scrollbar_mag.set)

        # 2. Liste des familles
        familles_frame = ttk.LabelFrame(lists_frame, text="📋 Familles (Catégories)")
        familles_frame.pack(side='right', fill='both', expand=True, padx=5)
        
        self.listbox_familles = tk.Listbox(familles_frame, selectmode=tk.MULTIPLE, exportselection=False)
        self.listbox_familles.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scrollbar_fam = ttk.Scrollbar(familles_frame, orient="vertical", command=self.listbox_familles.yview)
        scrollbar_fam.pack(side='right', fill='y')
        self.listbox_familles.config(yscrollcommand=scrollbar_fam.set)

        # Bouton Lancer
        btn_frame = ttk.Frame(self.tab_main)
        btn_frame.pack(fill='x', padx=5, pady=5)
        
        self.btn_start = ttk.Button(btn_frame, text="▶ Lancer le Scraping", command=self.start_scraping)
        self.btn_start.pack(pady=5)

        # 3. Zone de logs
        logs_frame = ttk.LabelFrame(self.tab_main, text="📝 Logs")
        logs_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.text_logs = tk.Text(logs_frame, height=15, state='disabled', bg="#f4f4f4")
        self.text_logs.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scrollbar_logs = ttk.Scrollbar(logs_frame, orient="vertical", command=self.text_logs.yview)
        scrollbar_logs.pack(side='right', fill='y')
        self.text_logs.config(yscrollcommand=scrollbar_logs.set)

    def create_settings_tab(self):
        """Génère le contenu de l'onglet Paramètres."""
        # Fichier Magasins
        frame_mag = ttk.Frame(self.tab_settings)
        frame_mag.pack(fill='x', padx=10, pady=5)
        ttk.Label(frame_mag, text="Fichier JSON Magasins:").pack(anchor='w')
        self.entry_mag_json = ttk.Entry(frame_mag, width=80)
        self.entry_mag_json.insert(0, self.config.get("magasins_json", ""))
        self.entry_mag_json.pack(side='left', fill='x', expand=True)
        ttk.Button(frame_mag, text="Parcourir", command=lambda: self.browse_file(self.entry_mag_json)).pack(side='right', padx=5)

        # Fichier Familles
        frame_fam = ttk.Frame(self.tab_settings)
        frame_fam.pack(fill='x', padx=10, pady=5)
        ttk.Label(frame_fam, text="Fichier JSON Familles (Catégories):").pack(anchor='w')
        self.entry_fam_json = ttk.Entry(frame_fam, width=80)
        self.entry_fam_json.insert(0, self.config.get("familles_json", ""))
        self.entry_fam_json.pack(side='left', fill='x', expand=True)
        ttk.Button(frame_fam, text="Parcourir", command=lambda: self.browse_file(self.entry_fam_json)).pack(side='right', padx=5)

        # Options de sauvegarde
        frame_save = ttk.LabelFrame(self.tab_settings, text="Options de sauvegarde")
        frame_save.pack(fill='x', padx=10, pady=5)

        # Cases à cocher pour le type de fichier
        self.var_save_json = tk.BooleanVar(value=self.config.get("save_json", True))
        ttk.Checkbutton(frame_save, text="Générer les fichiers JSON", variable=self.var_save_json).pack(anchor='w', padx=5, pady=2)
        
        self.var_save_excel = tk.BooleanVar(value=self.config.get("save_excel", True))
        ttk.Checkbutton(frame_save, text="Générer les fichiers Excel (XLSX)", variable=self.var_save_excel).pack(anchor='w', padx=5, pady=2)

        # Dossier JSON
        frame_dir_json = ttk.Frame(frame_save)
        frame_dir_json.pack(fill='x', padx=5, pady=2)
        ttk.Label(frame_dir_json, text="Dossier de base pour JSON:").pack(side='left')
        self.entry_dir_json = ttk.Entry(frame_dir_json)
        self.entry_dir_json.insert(0, self.config.get("dir_json", "DATA_EV/JSON"))
        self.entry_dir_json.pack(side='left', fill='x', expand=True, padx=5)
        ttk.Button(frame_dir_json, text="Dossier", command=lambda: self.browse_dir(self.entry_dir_json)).pack(side='right')

        # Dossier Excel
        frame_dir_excel = ttk.Frame(frame_save)
        frame_dir_excel.pack(fill='x', padx=5, pady=2)
        ttk.Label(frame_dir_excel, text="Dossier de base pour Excel:").pack(side='left')
        self.entry_dir_excel = ttk.Entry(frame_dir_excel)
        self.entry_dir_excel.insert(0, self.config.get("dir_excel", "DATA_EV/XLSX"))
        self.entry_dir_excel.pack(side='left', fill='x', expand=True, padx=5)
        ttk.Button(frame_dir_excel, text="Dossier", command=lambda: self.browse_dir(self.entry_dir_excel)).pack(side='right')

        # Fichier Base de données
        frame_db = ttk.Frame(self.tab_settings)
        frame_db.pack(fill='x', padx=10, pady=5)
        ttk.Label(frame_db, text="Fichier Base de Données (SQLite):").pack(anchor='w')
        self.entry_db_file = ttk.Entry(frame_db, width=80)
        self.entry_db_file.insert(0, self.config.get("db_file", "EauVive_prix.db"))
        self.entry_db_file.pack(side='left', fill='x', expand=True)
        ttk.Button(frame_db, text="Parcourir", command=lambda: self.browse_db_file(self.entry_db_file)).pack(side='right', padx=5)

        # Headless Mode (Navigation invisible)
        self.var_headless = tk.BooleanVar(value=self.config.get("headless", True))
        ttk.Checkbutton(
            self.tab_settings, 
            text="Mode Headless (Exécuter le navigateur en arrière-plan)", 
            variable=self.var_headless
        ).pack(anchor='w', padx=10, pady=5)

        # Bouton Sauvegarder
        ttk.Button(self.tab_settings, text="💾 Sauvegarder et Actualiser", command=self.save_and_refresh).pack(pady=10)

    def browse_db_file(self, entry_widget):
        filename = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")],
            initialdir=os.getcwd()
        )
        if filename:
            entry_widget.delete(0, tk.END)
            try:
                rel_path = os.path.relpath(filename, os.getcwd())
                entry_widget.insert(0, rel_path)
            except:
                entry_widget.insert(0, filename)

    def browse_file(self, entry_widget):
        """Ouvre une boîte de dialogue pour sélectionner un fichier JSON."""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=os.getcwd()
        )
        if filename:
            entry_widget.delete(0, tk.END)
            # Utilise un chemin relatif si possible, sinon le chemin absolu
            try:
                rel_path = os.path.relpath(filename, os.getcwd())
                entry_widget.insert(0, rel_path)
            except:
                entry_widget.insert(0, filename)

    def browse_dir(self, entry_widget):
        """Ouvre une boîte de dialogue pour sélectionner un dossier."""
        dirname = filedialog.askdirectory(initialdir=os.getcwd())
        if dirname:
            entry_widget.delete(0, tk.END)
            try:
                rel_path = os.path.relpath(dirname, os.getcwd())
                entry_widget.insert(0, rel_path)
            except:
                entry_widget.insert(0, dirname)

    def save_and_refresh(self):
        """Sauvegarde les paramètres et rafraîchit les listes."""
        self.config["magasins_json"] = self.entry_mag_json.get()
        self.config["familles_json"] = self.entry_fam_json.get()
        self.config["headless"] = self.var_headless.get()
        self.config["save_json"] = self.var_save_json.get()
        self.config["save_excel"] = self.var_save_excel.get()
        self.config["dir_json"] = self.entry_dir_json.get()
        self.config["dir_excel"] = self.entry_dir_excel.get()
        self.config["db_file"] = self.entry_db_file.get()
        self.save_config()
        self.refresh_lists()
        messagebox.showinfo("Succès", "Paramètres sauvegardés et listes actualisées.")
        self.notebook.select(self.tab_main)

    def log(self, message):
        """Ajoute un message dans la zone de texte des logs."""
        self.text_logs.config(state='normal')
        self.text_logs.insert(tk.END, message + "\n")
        self.text_logs.see(tk.END)
        self.text_logs.config(state='disabled')
        # Force l'UI à se mettre à jour (utile si exécuté dans le thread principal, 
        # mais ici on l'appellera majoritairement depuis le thread secondaire)
        # self.root.update() est safe si appelé précautionneusement, mais on peut s'en passer.

    def refresh_lists(self):
        """Vide et recharge les Listbox avec les fichiers JSON spécifiés dans les paramètres."""
        self.listbox_magasins.delete(0, tk.END)
        self.listbox_familles.delete(0, tk.END)

        # Charger magasins
        magasins = charger_json(self.config["magasins_json"], self.log)
        self.magasins_data = []
        if magasins and isinstance(magasins, list):
            for m in magasins:
                if isinstance(m, dict) and m.get("denomination"):
                    self.magasins_data.append(m)
                    nom = m.get("denomination")
                    ville = m.get("ville", "")
                    self.listbox_magasins.insert(tk.END, f"{nom} - {ville}")
        
        # Charger familles
        familles = charger_json(self.config["familles_json"], self.log)
        self.familles_data = []
        if familles and isinstance(familles, list):
            for f in familles:
                if isinstance(f, dict):
                    self.familles_data.append(f)
                    nom = f.get("Famille", "Inconnu")
                    self.listbox_familles.insert(tk.END, nom)

    def start_scraping(self):
        """Vérifie la sélection et lance le thread de scraping."""
        sel_mag_indices = self.listbox_magasins.curselection()
        sel_fam_indices = self.listbox_familles.curselection()

        if not sel_mag_indices:
            messagebox.showwarning("Attention", "Veuillez sélectionner au moins un magasin.")
            return
        if not sel_fam_indices:
            messagebox.showwarning("Attention", "Veuillez sélectionner au moins une famille.")
            return

        magasins_choisis = [str(self.magasins_data[i]["denomination"]).strip() for i in sel_mag_indices]
        familles_choisies = [self.familles_data[i] for i in sel_fam_indices]

        # Désactiver le bouton et nettoyer les logs
        self.btn_start.config(state='disabled')
        self.text_logs.config(state='normal')
        self.text_logs.delete(1.0, tk.END)
        self.text_logs.config(state='disabled')
        
        # Lancer dans un thread séparé pour ne pas geler l'interface graphique
        threading.Thread(target=self.run_scraping_task, args=(magasins_choisis, familles_choisies), daemon=True).start()

    def run_scraping_task(self, magasins, familles):
        """Routine exécutée dans le thread de fond pour le scraping."""
        self.log("="*70)
        self.log("🚀 DÉMARRAGE DU SCRAPING (V6)")
        self.log(f"🏪 Magasins sélectionnés : {len(magasins)}")
        self.log(f"📋 Familles sélectionnées : {len(familles)}")
        self.log("="*70 + "\n")

        headless = self.config.get("headless", True)

        for idx, magasin in enumerate(magasins):
            self.log(f"\n" + "="*70)
            self.log(f"🛒 TRAITEMENT DU MAGASIN [{idx+1}/{len(magasins)}] : {magasin}")
            self.log("="*70)
            
            try:
                # Connexion au magasin via selenium
                driver = get_connected_driver(magasin, headless=headless)
                if not driver:
                    self.log(f"⚠️ Impossible de se connecter au magasin {magasin}.")
                    continue

                for j, famille in enumerate(familles):
                    nom_famille = famille.get("Famille", "Famille")
                    url = famille.get("lien")
                    
                    if not url:
                        self.log(f"❌ Aucun lien pour la famille '{nom_famille}'")
                        continue
                        
                    self.log(f"\n📌 SCRAPING : {nom_famille} (URL: {url})")
                    scraper = ScraperV6(driver, url, log_callback=self.log)
                    
                    if scraper.run():
                        scraper.save_data(
                            nom_famille, 
                            magasin,
                            save_json=self.config.get("save_json", True),
                            save_excel=self.config.get("save_excel", True),
                            dir_json=self.config.get("dir_json", "DATA_EV/JSON"),
                            dir_excel=self.config.get("dir_excel", "DATA_EV/XLSX")
                        )
                    else:
                        self.log(f"❌ Échec du scraping pour '{nom_famille}'.")

                # Fermer le navigateur pour ce magasin
                self.log(f"\n🔒 Fermeture de la connexion pour {magasin}")
                driver.quit()
                
            except Exception as e:
                self.log(f"❌ Erreur inattendue pour le magasin {magasin} : {e}")

        self.log("\n" + "="*70)
        self.log("🎉 TRAITEMENT GLOBAL TERMINÉ")
        self.log("="*70)
        
        # Réactiver le bouton (en passant par le thread principal)
        self.root.after(0, lambda: self.btn_start.config(state='normal'))
        self.root.after(0, lambda: messagebox.showinfo("Terminé", "Le scraping est terminé ! Les fichiers sont dans DATA_EV/"))
