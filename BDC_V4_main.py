"""
Point d'entrée : CLI + GUI.
"""
import argparse
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, scrolledtext

from utils.gestionnaire_db import GestionnaireDB
from utils.export_produits import (
    exporter_produits_magasin_json,
    exporter_tous_magasins_json,
)


# =====================================================================
#  GUI
# =====================================================================
class ApplicationGUI:
    def __init__(self, root, db_path="EauVive_prix.db", is_tab=False):
        self.root = root
        self.is_tab = is_tab
        if not self.is_tab:
            self.root.title("Gestionnaire de Catalogue Eau Vive")
            self.root.geometry("900x700")

        self.db = GestionnaireDB(db_path)
        self.fichiers_selectionnes = []
        self.importation_en_cours = False
        self.message_queue = queue.Queue()

        # Magasin par défaut
        self.magasin_id = self.db.creer_magasin(
            "Eau Vive", nomcsv="Eau Vive",
            adresse="Magasin bio", ville="France",
            livraison_domicile=1, retrait_magasin=1
        )

        self.creer_interface()
        self.mettre_a_jour_statistiques()
        self.traiter_messages()

    # ------------------------------------------------------------------
    def creer_interface(self):
        if not self.is_tab:
            menubar = tk.Menu(self.root)
            self.root.config(menu=menubar)

            file_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="Fichier", menu=file_menu)
            file_menu.add_command(label="Importer des JSON",
                                  command=self.selectionner_fichiers)
            file_menu.add_separator()
            file_menu.add_command(label="Exporter les produits par magasin",
                                  command=self.exporter_produits)
            file_menu.add_separator()
            file_menu.add_command(label="Vérifier sans description",
                                  command=self.verifier_sans_description)
            file_menu.add_separator()
            file_menu.add_command(label="Quitter", command=self.quitter)

        # ----- Frame principal -----
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # La racine s'étend
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Le main_frame s'étend
        main_frame.columnconfigure(0, weight=1)
        # Seule la ligne du journal (row=3 pour window, row=4 pour tab) doit prendre l'espace vertical
        log_row = 4 if self.is_tab else 3
        main_frame.rowconfigure(log_row, weight=1)

        title = ttk.Label(main_frame,
                          text="Gestionnaire de Catalogue Eau Vive",
                          font=('Arial', 16, 'bold'))
        title.grid(row=0, column=0, columnspan=2, pady=10)

        # ----- Toolbar (uniquement en mode tab) -----
        current_row = 1
        if self.is_tab:
            toolbar = ttk.Frame(main_frame)
            toolbar.grid(row=current_row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
            ttk.Button(toolbar, text="📥 Importer des JSON", command=self.selectionner_fichiers).pack(side=tk.LEFT, padx=5)
            ttk.Button(toolbar, text="📤 Exporter les produits", command=self.exporter_produits).pack(side=tk.LEFT, padx=5)
            ttk.Button(toolbar, text="🔍 Vérifier", command=self.verifier_sans_description).pack(side=tk.LEFT, padx=5)
            self.btn_dashboard = ttk.Button(toolbar, text="📊 Lancer Dashboard", command=self.lancer_dashboard)
            self.btn_dashboard.pack(side=tk.LEFT, padx=5)
            current_row += 1

        # ----- Statistiques -----
        stats_frame = ttk.LabelFrame(main_frame, text="Statistiques", padding="10")
        stats_frame.grid(row=current_row, column=0, columnspan=2,
                         sticky=(tk.W, tk.E), pady=10)
        current_row += 1

        self.stats_labels = {}
        stats = ['produits', 'releves', 'magasins', 'categories', 'sans_description']
        labels = ['Produits', 'Relevés', 'Magasins', 'Catégories', 'Sans desc.']
        for i, (stat, label) in enumerate(zip(stats, labels)):
            ttk.Label(stats_frame, text=f"{label} :").grid(
                row=0, column=i * 2, padx=5
            )
            self.stats_labels[stat] = ttk.Label(stats_frame, text="0")
            self.stats_labels[stat].grid(row=0, column=i * 2 + 1, padx=5)

        # ----- Importation -----
        import_frame = ttk.LabelFrame(main_frame, text="Importation JSON",
                                      padding="10")
        import_frame.grid(row=current_row, column=0, columnspan=2,
                          sticky=(tk.W, tk.E), pady=10)
        current_row += 1

        # Pour que la liste des fichiers s'étende horizontalement
        import_frame.columnconfigure(0, weight=1)

        btn_frame = ttk.Frame(import_frame)
        btn_frame.grid(row=0, column=0, columnspan=3, pady=5)

        self.btn_selectionner = ttk.Button(
            btn_frame, text="📁 Sélectionner des fichiers JSON",
            command=self.selectionner_fichiers)
        self.btn_selectionner.pack(side=tk.LEFT, padx=5)

        self.btn_importer = ttk.Button(
            btn_frame, text="🚀 Importer",
            command=self.importer_fichiers)
        self.btn_importer.pack(side=tk.LEFT, padx=5)

        self.btn_vider = ttk.Button(
            btn_frame, text="🗑️ Vider la liste",
            command=self.vider_liste)
        self.btn_vider.pack(side=tk.LEFT, padx=5)

        self.progress_bar = ttk.Progressbar(import_frame, mode='indeterminate')
        self.progress_bar.grid(row=1, column=0, columnspan=3,
                               sticky=(tk.W, tk.E), pady=5)

        ttk.Label(import_frame, text="Fichiers sélectionnés :").grid(
            row=2, column=0, sticky=tk.W, pady=5)

        list_frame = ttk.Frame(import_frame)
        list_frame.grid(row=3, column=0, columnspan=3,
                        sticky=(tk.W, tk.E), pady=5)
        list_frame.columnconfigure(0, weight=1)

        self.liste_fichiers = tk.Listbox(list_frame, height=5, width=80)
        self.liste_fichiers.grid(row=0, column=0, sticky=(tk.W, tk.E))
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                  command=self.liste_fichiers.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.liste_fichiers.config(yscrollcommand=scrollbar.set)

        # ----- Journal -----
        log_frame = ttk.LabelFrame(main_frame, text="📋 Journal", padding="10")
        log_frame.grid(row=current_row, column=0, columnspan=2,
                       sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        current_row += 1
        # Le log_frame doit s'étendre dans les deux directions
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame,
                                                  height=10, width=80,
                                                  wrap=tk.WORD)
        self.log_text.grid(row=0, column=0,
                           sticky=(tk.W, tk.E, tk.N, tk.S))

        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.grid(row=1, column=0, pady=5)

        ttk.Button(log_btn_frame, text="📄 Exporter le journal",
                   command=self.exporter_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(log_btn_frame, text="🗑️ Effacer le journal",
                   command=self.effacer_log).pack(side=tk.LEFT, padx=5)

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
        prefix = {'info': 'ℹ️', 'success': '✅',
                  'error': '❌', 'warning': '⚠️'}.get(type_message, 'ℹ️')
        self.log_text.tag_config('info', foreground='black')
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')
        self.log_text.tag_config('warning', foreground='orange')
        self.log_text.insert(tk.END,
                             f"[{timestamp}] {prefix} {message}\n",
                             type_message)
        self.log_text.see(tk.END)

    def exporter_log(self):
        filename = filedialog.asksaveasfilename(
            title="Exporter le journal", defaultextension=".txt",
            filetypes=[("Fichiers texte", "*.txt"), ("Tous", "*.*")])
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, tk.END))
                messagebox.showinfo("Succès", f"Journal exporté vers {filename}")
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur : {e}")

    def effacer_log(self):
        if messagebox.askyesno("Effacer", "Effacer le journal ?"):
            self.log_text.delete(1.0, tk.END)
            self.log("Journal effacé", 'info')

    def lancer_dashboard(self):
        import subprocess
        try:
            if hasattr(self, 'streamlit_process') and self.streamlit_process is not None:
                # Le dashboard est déjà lancé, on l'arrête
                self.streamlit_process.terminate()
                self.streamlit_process = None
                if hasattr(self, 'btn_dashboard'):
                    self.btn_dashboard.config(text="📊 Lancer Dashboard")
                self.log("Dashboard Streamlit arrêté.", "info")
                return

            # CREATE_NO_WINDOW permet de ne pas ouvrir une console noire sous Windows
            creation_flags = 0x08000000 if os.name == 'nt' else 0
            
            # On pipe stdout et stderr vers DEVNULL pour éviter que le processus plante sans console
            self.streamlit_process = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run", "DashBoard_EV3.py"],
                cwd=os.getcwd(),
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            if hasattr(self, 'btn_dashboard'):
                self.btn_dashboard.config(text="🛑 Arrêter Dashboard")
                
            self.log("Lancement de Streamlit en arrière-plan...", "info")
            messagebox.showinfo("Dashboard", "Le Dashboard Streamlit se lance en arrière-plan.\n\nIl va s'ouvrir dans votre navigateur d'ici quelques secondes.")
            
            # Forcer l'ouverture du navigateur au cas où Streamlit ne le ferait pas automatiquement
            import webbrowser
            import threading
            threading.Timer(3.0, lambda: webbrowser.open("http://localhost:8501")).start()

        except Exception as e:
            self.log(f"Erreur au lancement/arrêt du Dashboard : {e}", "error")
            messagebox.showerror("Erreur", f"Impossible de gérer le Dashboard :\n{e}")

    def mettre_a_jour_statistiques(self):
        stats = self.db.get_statistiques()
        for key, value in stats.items():
            if key in self.stats_labels:
                self.stats_labels[key].config(text=str(value))

    # ------------------------------------------------------------------
    def selectionner_fichiers(self):
        fichiers = filedialog.askopenfilenames(
            title="Sélectionner les fichiers JSON",
            filetypes=[("Fichiers JSON", "*.json"), ("Tous", "*.*")])
        if fichiers:
            for fichier in fichiers:
                if fichier not in self.fichiers_selectionnes:
                    self.fichiers_selectionnes.append(fichier)
                    self.liste_fichiers.insert(tk.END, os.path.basename(fichier))
            self.log(f"{len(fichiers)} fichier(s) ajouté(s)", 'info')

    def vider_liste(self):
        self.fichiers_selectionnes.clear()
        self.liste_fichiers.delete(0, tk.END)
        self.log("Liste vidée", 'info')

    def verifier_sans_description(self):
        produits = self.db.verifier_produits_sans_description()
        if not produits:
            messagebox.showinfo("Info", "Tous les produits ont une description.")
            return
        fenetre = tk.Toplevel(self.root)
        fenetre.title("Produits sans description")
        fenetre.geometry("600x400")
        frame = ttk.Frame(fenetre, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=f"{len(produits)} produit(s) sans description :",
                  font=('Arial', 10, 'bold')).pack(pady=5)
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

    # ------------------------------------------------------------------
    def importer_fichiers(self):
        if not self.fichiers_selectionnes:
            messagebox.showwarning("Aucun fichier",
                                   "Sélectionnez des fichiers à importer.")
            return
        if self.importation_en_cours:
            messagebox.showwarning("En cours", "Importation déjà en cours.")
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
                total = len(fichiers_a_importer)

                for idx, fichier in enumerate(fichiers_a_importer):
                    nom = os.path.basename(fichier)
                    self.log(f"[{idx + 1}/{total}] Importation de {nom}...", 'info')

                    def callback(message, type_message, nf=nom):
                        self.log(f"{nf}: {message}", type_message)

                    success = self.db.importer_fichier_json(
                        fichier, callback=callback)
                    if not success:
                        fichiers_erreur.append(nom)

                self.root.after(0, self.mettre_a_jour_statistiques)

                if fichiers_erreur:
                    self.log(f"⚠️ {len(fichiers_erreur)} fichier(s) en erreur",
                             'warning')
                else:
                    self.log("✅ Tous les fichiers importés !", 'success')

                self.root.after(0, lambda: messagebox.showinfo(
                    "Succès",
                    f"Importation terminée.\n"
                    f"{len(fichiers_erreur)} fichier(s) en erreur."))

            except Exception as e:
                self.log(f"Erreur fatale : {e}", 'error')
                self.root.after(0, lambda: messagebox.showerror(
                    "Erreur", f"Une erreur est survenue : {e}"))
            finally:
                self.root.after(0, self.fin_importation)

        threading.Thread(target=importer, daemon=True).start()

    def fin_importation(self):
        self.importation_en_cours = False
        self.btn_selectionner.config(state='normal')
        self.btn_importer.config(state='normal')
        self.btn_vider.config(state='normal')
        self.progress_bar.stop()

    # ------------------------------------------------------------------
    def exporter_produits(self):
        """Ouvre une boîte de dialogue pour exporter les produits."""
        fenetre = tk.Toplevel(self.root)
        fenetre.title("Exporter les produits par magasin")
        fenetre.geometry("500x320")
        fenetre.transient(self.root)
        fenetre.grab_set()

        frame = ttk.Frame(fenetre, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Magasin :").grid(row=0, column=0,
                                                sticky=tk.W, pady=5)
        conn, cursor = self.db._get_connection()
        cursor.execute("SELECT id, nom FROM MAGASINS ORDER BY nom")
        magasins = cursor.fetchall()

        magasin_var = tk.StringVar()
        combo = ttk.Combobox(
            frame,
            textvariable=magasin_var,
            values=[f"{m[0]} - {m[1]}" for m in magasins],
            state="readonly", width=40)
        combo.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        if magasins:
            combo.current(0)

        ttk.Label(frame, text="Date max (optionnel, YYYY-MM-DD) :").grid(
            row=1, column=0, sticky=tk.W, pady=5)
        date_var = tk.StringVar()
        ttk.Entry(frame, textvariable=date_var, width=42).grid(
            row=1, column=1, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(frame, text="Fichier de sortie :").grid(
            row=2, column=0, sticky=tk.W, pady=5)
        chemin_var = tk.StringVar(value=os.path.abspath("export_produits.json"))
        ttk.Entry(frame, textvariable=chemin_var, width=42).grid(
            row=2, column=1, sticky=(tk.W, tk.E), pady=5)

        def choisir_fichier():
            chemin = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("Tous", "*.*")],
                initialfile="export_produits.json")
            if chemin:
                chemin_var.set(chemin)

        ttk.Button(frame, text="Parcourir...", command=choisir_fichier).grid(
            row=2, column=2, padx=5)

        def lancer_export():
            if not magasin_var.get():
                messagebox.showwarning("Aucun magasin", "Sélectionnez un magasin.")
                return
            magasin_id = int(magasin_var.get().split(" - ")[0])
            date_max = date_var.get().strip() or None
            chemin = chemin_var.get().strip()
            if not chemin:
                messagebox.showwarning("Chemin", "Indiquez un fichier de sortie.")
                return

            ok = exporter_produits_magasin_json(
                self.db, magasin_id, chemin,
                date_max=date_max,
                callback=self.log)
            if ok:
                messagebox.showinfo("Succès", f"Exporté vers {chemin}")
                fenetre.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=15)
        ttk.Button(btn_frame, text="Exporter",
                   command=lancer_export).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Exporter tous les magasins",
                   command=lambda: self.exporter_tous(magasins, date_var.get().strip() or None)
                   ).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Annuler",
                   command=fenetre.destroy).pack(side=tk.LEFT, padx=5)

    def exporter_tous(self, magasins, date_max):
        dossier = filedialog.askdirectory(title="Dossier de sortie")
        if not dossier:
            return
        fichiers = exporter_tous_magasins_json(
            self.db, dossier, date_max=date_max, callback=self.log)
        messagebox.showinfo("Succès",
                            f"{len(fichiers)} fichier(s) exporté(s) dans {dossier}")

    # ------------------------------------------------------------------
    def quitter(self):
        if self.importation_en_cours:
            if not messagebox.askokcancel(
                    "Quitter", "Importation en cours. Quitter ?"):
                return
        if messagebox.askokcancel("Quitter", "Voulez-vous vraiment quitter ?"):
            self.db.fermer()
            self.root.quit()


# =====================================================================
#  CLI
# =====================================================================
def interface_cli():
    parser = argparse.ArgumentParser(
        description="Gestionnaire de catalogue Eau Vive")
    parser.add_argument("--import", dest="fichiers", nargs="+",
                        help="Fichiers JSON à importer")
    parser.add_argument("--magasin", default="Eau Vive",
                        help="Nom du magasin")
    parser.add_argument("--stats", action="store_true",
                        help="Afficher les statistiques")
    parser.add_argument("--db", default="EauVive_prix.db",
                        help="Chemin de la base")
    parser.add_argument("--export-magasin", type=int, default=None,
                        help="ID du magasin à exporter")
    parser.add_argument("--export-tous", action="store_true",
                        help="Exporter tous les magasins")
    parser.add_argument("--export-dossier", default="exports",
                        help="Dossier d'export")
    parser.add_argument("--export-date-max", default=None,
                        help="Date max (YYYY-MM-DD)")
    parser.add_argument("--init-db", action="store_true",
                        help="Initialiser le schéma de la base")

    args = parser.parse_args()

    if args.init_db:
        from utils.schema_db import creer_base
        creer_base(args.db)
        return

    try:
        db = GestionnaireDB(args.db)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)

    try:
        db.creer_magasin(args.magasin, nomcsv=args.magasin)

        if args.fichiers:
            print("\n=== Importation ===")
            for fichier in args.fichiers:
                print(f"\nImportation de {fichier}...")
                db.importer_fichier_json(fichier)

        if args.export_magasin is not None:
            chemin = os.path.join(
                args.export_dossier,
                f"magasin_{args.export_magasin}.json")
            exporter_produits_magasin_json(
                db, args.export_magasin, chemin,
                date_max=args.export_date_max,
                callback=lambda m, t: print(f"[{t}] {m}"))

        if args.export_tous:
            fichiers = exporter_tous_magasins_json(
                db, args.export_dossier,
                date_max=args.export_date_max,
                callback=lambda m, t: print(f"[{t}] {m}"))
            print(f"\n{len(fichiers)} fichier(s) exporté(s).")

        if args.stats:
            stats = db.get_statistiques()
            print("\n=== Statistiques ===")
            for k, v in stats.items():
                print(f"{k} : {v}")
            print("===================")

    finally:
        db.fermer()


def interface_gui():
    root = tk.Tk()
    app = ApplicationGUI(root)
    root.mainloop()


def main():
    if len(sys.argv) > 1:
        interface_cli()
    else:
        interface_gui()


if __name__ == "__main__":
    main()