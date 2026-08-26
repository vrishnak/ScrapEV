import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from bs4 import BeautifulSoup
import pandas as pd
import re
import threading
import os
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================
HEADERS = {
    'User-Agent': 'ScrapBIO_Product_Matcher/1.0 (contact@example.com)',
    'Accept': 'application/json',
    'Accept-Language': 'fr-FR,fr;q=0.9'
}
DELAI_ENTRE_REQUETES = 30
TIMEOUT = 10
MAX_RETRIES = 2

# Dossier de destination des CSV
OUTPUT_DIR = "DATA_EV/CSV"


# ============================================================
# CLASSE DE L'INTERFACE GRAPHIQUE
# ============================================================
class HtmlProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("📦 Analyseur de produits Eau-Vive")
        self.root.geometry("900x700")
        self.root.resizable(True, True)

        # Variables
        self.files_list = []
        self.processing = False

        # Création du dossier de sortie s'il n'existe pas
        self.create_output_directory()

        # Configuration du style
        self.setup_styles()

        # Création de l'interface
        self.create_widgets()

    def create_output_directory(self):
        """Crée le dossier de sortie s'il n'existe pas"""
        try:
            Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Erreur lors de la création du dossier {OUTPUT_DIR}: {e}")

    def setup_styles(self):
        """Configure les styles de l'interface"""
        style = ttk.Style()
        style.theme_use('clam')

        # Couleurs
        self.bg_color = "#f0f0f0"
        self.primary_color = "#2c3e50"
        self.success_color = "#27ae60"
        self.error_color = "#e74c3c"

        self.root.configure(bg=self.bg_color)

    def create_widgets(self):
        """Crée tous les widgets de l'interface"""

        # Frame principal avec padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Titre
        title_label = ttk.Label(
            main_frame,
            text="📦 Analyseur de produits Eau-Vive",
            font=('Arial', 16, 'bold')
        )
        title_label.pack(pady=(0, 10))

        # Frame de sélection des fichiers
        file_frame = ttk.LabelFrame(main_frame, text="📁 Sélection des fichiers HTML", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        # Boutons d'ajout/suppression
        button_frame = ttk.Frame(file_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(
            button_frame,
            text="➕ Ajouter des fichiers",
            command=self.add_files
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            button_frame,
            text="🗑️ Supprimer sélection",
            command=self.remove_selected
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            button_frame,
            text="🧹 Vider la liste",
            command=self.clear_files
        ).pack(side=tk.LEFT, padx=(0, 5))

        # Liste des fichiers avec scrollbar
        list_frame = ttk.Frame(file_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.file_listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            height=6,
            font=('Arial', 10)
        )
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        # Compteur de fichiers
        self.file_count_label = ttk.Label(file_frame, text="0 fichier(s) sélectionné(s)")
        self.file_count_label.pack(pady=(5, 0))

        # Informations sur le dossier de sortie
        info_frame = ttk.LabelFrame(main_frame, text="📂 Informations", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            info_frame,
            text=f"Dossier de sauvegarde : {OUTPUT_DIR}",
            font=('Arial', 10)
        ).pack(anchor=tk.W)

        ttk.Label(
            info_frame,
            text="Les fichiers CSV seront sauvegardés automatiquement avec le même nom",
            font=('Arial', 9),
            foreground="gray"
        ).pack(anchor=tk.W)

        # Bouton de lancement
        self.process_button = ttk.Button(
            main_frame,
            text="🚀 Lancer le traitement",
            command=self.start_processing,
            style='Accent.TButton'
        )
        self.process_button.pack(pady=(0, 10))

        # Zone de log
        log_frame = ttk.LabelFrame(main_frame, text="📝 Journal d'exécution", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=15,
            font=('Consolas', 10),
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Barre de progression
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            main_frame,
            variable=self.progress_var,
            maximum=100,
            length=100
        )
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))

        # Ajouter un bouton pour effacer les logs
        ttk.Button(
            main_frame,
            text="🗑️ Effacer les logs",
            command=self.clear_logs
        ).pack(pady=(5, 0))

        # Ajouter un bouton pour ouvrir le dossier de sortie
        ttk.Button(
            main_frame,
            text="📂 Ouvrir le dossier de sortie",
            command=self.open_output_folder
        ).pack(pady=(5, 0))

    def add_files(self):
        """Ajoute des fichiers à la liste"""
        files = filedialog.askopenfilenames(
            title="Sélectionner des fichiers HTML",
            filetypes=[("Fichiers HTML", "*.html"), ("Tous les fichiers", "*.*")]
        )

        if files:
            for file in files:
                if file not in self.files_list:
                    self.files_list.append(file)
                    self.file_listbox.insert(tk.END, Path(file).name)

            self.update_file_count()
            self.log(f"✅ {len(files)} fichier(s) ajouté(s)")

    def remove_selected(self):
        """Supprime les fichiers sélectionnés"""
        selected = self.file_listbox.curselection()
        if selected:
            # Supprimer en ordre inverse pour éviter les problèmes d'index
            for index in reversed(selected):
                del self.files_list[index]
                self.file_listbox.delete(index)

            self.update_file_count()
            self.log(f"🗑️ {len(selected)} fichier(s) supprimé(s)")

    def clear_files(self):
        """Vide toute la liste"""
        if self.files_list:
            if messagebox.askyesno("Confirmation", "Voulez-vous vraiment vider toute la liste ?"):
                self.files_list.clear()
                self.file_listbox.delete(0, tk.END)
                self.update_file_count()
                self.log("🧹 Liste vidée")

    def update_file_count(self):
        """Met à jour le compteur de fichiers"""
        count = len(self.files_list)
        self.file_count_label.config(text=f"{count} fichier(s) sélectionné(s)")

    def log(self, message, level="INFO"):
        """Ajoute un message dans la zone de log"""
        timestamp = pd.Timestamp.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def clear_logs(self):
        """Efface la zone de log"""
        self.log_text.delete(1.0, tk.END)

    def open_output_folder(self):
        """Ouvre le dossier de sortie dans l'explorateur de fichiers"""
        try:
            if os.name == 'nt':  # Windows
                os.startfile(OUTPUT_DIR)
            elif os.name == 'posix':  # macOS et Linux
                import subprocess
                subprocess.Popen(['open', OUTPUT_DIR]) if sys.platform == 'darwin' else subprocess.Popen(
                    ['xdg-open', OUTPUT_DIR])
        except Exception as e:
            self.log(f"❌ Impossible d'ouvrir le dossier : {str(e)}", "ERROR")

    def start_processing(self):
        """Démarre le traitement dans un thread séparé"""
        if self.processing:
            messagebox.showwarning("En cours", "Un traitement est déjà en cours")
            return

        if not self.files_list:
            messagebox.showwarning("Aucun fichier", "Veuillez sélectionner au moins un fichier HTML")
            return

        # Désactiver le bouton pendant le traitement
        self.process_button.config(state=tk.DISABLED, text="⏳ Traitement en cours...")
        self.progress_var.set(0)
        self.processing = True

        # Lancer le traitement dans un thread
        thread = threading.Thread(target=self.process_files)
        thread.daemon = True
        thread.start()

    def process_files(self):
        """Traite tous les fichiers sélectionnés"""
        try:
            total_files = len(self.files_list)
            success_count = 0

            for i, filepath in enumerate(self.files_list):
                self.log(f"📄 Traitement de : {Path(filepath).name}")

                try:
                    # Lire le fichier HTML
                    with open(filepath, 'r', encoding='utf-8') as f:
                        html_content = f.read()

                    # Extraire les produits
                    df = self.extract_products_eauvive(html_content)

                    if not df.empty:
                        # Ajouter une colonne avec le nom du fichier source
                        df['source_file'] = Path(filepath).name

                        # Exporter automatiquement en CSV
                        csv_filename = self.export_to_csv(df, filepath)
                        success_count += 1
                        self.log(f"   ✓ {len(df)} produits extraits et sauvegardés dans : {csv_filename}")
                    else:
                        self.log(f"   ⚠️ Aucun produit trouvé dans ce fichier")

                except Exception as e:
                    self.log(f"   ❌ Erreur : {str(e)}", "ERROR")

                # Mettre à jour la progression
                progress = ((i + 1) / total_files) * 100
                self.progress_var.set(progress)

            self.log(f"\n✅ Traitement terminé ! {success_count}/{total_files} fichiers traités avec succès")
            self.log(f"📂 Tous les CSV ont été sauvegardés dans : {OUTPUT_DIR}")

            # Demander si l'utilisateur veut ouvrir le dossier
            if success_count > 0:
                if messagebox.askyesno("Succès",
                                       f"{success_count} fichier(s) traité(s) avec succès.\nVoulez-vous ouvrir le dossier de sortie ?"):
                    self.open_output_folder()

        except Exception as e:
            self.log(f"❌ Erreur lors du traitement : {str(e)}", "ERROR")
            messagebox.showerror("Erreur", f"Une erreur est survenue :\n{str(e)}")

        finally:
            # Réactiver l'interface
            self.processing = False
            self.root.after(0, self.enable_ui)

    def enable_ui(self):
        """Réactive l'interface après le traitement"""
        self.process_button.config(state=tk.NORMAL, text="🚀 Lancer le traitement")
        self.progress_var.set(0)

    def export_to_csv(self, df, html_filepath):
        """Exporte le DataFrame en CSV avec le même nom que le fichier HTML dans le dossier DATA_EV/CSV"""
        # Récupérer le nom du fichier sans extension
        base_name = Path(html_filepath).stem

        # Créer le chemin complet du fichier CSV
        csv_path = Path(OUTPUT_DIR) / f"{base_name}.csv"

        # Exporter en CSV
        df.to_csv(csv_path, index=False, encoding='utf-8-sig', sep=';')

        return str(csv_path)

    # ============================================================
    # FONCTIONS D'EXTRACTION (copiées de votre code)
    # ============================================================
    def extract_products_eauvive(self, html_content):
        """Analyse le code HTML et extrait les informations des produits."""
        soup = BeautifulSoup(html_content, "html.parser")
        products = []

        for card in soup.select("div.product-card"):
            product = {}

            # Nom et référence
            title_div = card.select_one("div.product-title")
            if title_div:
                title_link = title_div.select_one("a")
                if title_link:
                    product["name"] = title_link.get_text(strip=True)
                    product["url"] = f"https://eau-vive.com{title_link.get('href')}"
                    ref_match = re.search(r'_(\d+)$', product["url"]) if product["url"] else None
                    product["ref_id"] = ref_match.group(1) if ref_match else None

            # Image Eau-Vive
            img_link = card.select_one("a.img-link")
            product["img_eauvive_url"] = None
            product["img_eauvive_alt"] = None

            if img_link:
                img_tag = img_link.select_one("img")
                if img_tag:
                    img_src = img_tag.get("src") or img_tag.get("data-src")
                    if img_src:
                        if img_src.startswith('//'):
                            product["img_eauvive_url"] = f"https:{img_src}"
                        elif img_src.startswith('/'):
                            product["img_eauvive_url"] = f"https://api.eau-vive.com{img_src}"
                        else:
                            product["img_eauvive_url"] = img_src
                        product["img_eauvive_alt"] = img_tag.get("alt")

            # EAN : toujours NULL
            product["ean"] = None

            # Badges/Flags
            card_state = card.select_one("div.card-state")
            badges = []
            flags = []
            if card_state:
                for img in card_state.select("img"):
                    img_src = img.get("src") or img.get("data-src")
                    if img_src:
                        if img_src.startswith('//'):
                            full_url = f"https:{img_src}"
                        elif img_src.startswith('/'):
                            full_url = f"https://api.eau-vive.com{img_src}"
                        else:
                            full_url = img_src
                        badges.append(full_url)
                        if 'promo' in full_url.lower() or 'badge' in full_url.lower():
                            flags.append(full_url)
            product["badges"] = badges
            product["flags"] = flags

            # Promotion
            product["is_promo"] = card.select_one("div.promotion-badge") is not None

            # Prix
            price_span = card.select_one("span.product-price")
            if price_span:
                price_text = price_span.get_text(strip=True).replace("€", "").replace(",", ".")
                try:
                    product["price"] = float(price_text)
                except ValueError:
                    product["price"] = None

            # Prix barré
            price_old_span = card.select_one("span.product-not-price")
            if price_old_span:
                price_old_text = price_old_span.get_text(strip=True).replace("€", "").replace(",", ".")
                try:
                    product["price_old"] = float(price_old_text)
                except ValueError:
                    product["price_old"] = None

            # Volume et prix unitaire
            price_types = card.select("span.product-price-type")
            if len(price_types) >= 1:
                product["volume"] = price_types[0].get_text(strip=True)
            if len(price_types) >= 2:
                product["price_unit"] = price_types[1].get_text(strip=True)

            # Tags
            tags = []
            for tag in card.select("span.product-regime-tag"):
                tag_text = tag.get_text(strip=True)
                if tag_text:
                    icon = tag.select_one("img")
                    if icon:
                        icon_src = icon.get("src")
                        tags.append({'text': tag_text, 'icon': icon_src})
                    else:
                        tags.append(tag_text)
            product["tags"] = tags

            # Marque : toujours NULL
            product["brand"] = None

            products.append(product)

        return pd.DataFrame(products)


# ============================================================
# FONCTION PRINCIPALE
# ============================================================
def main():
    root = tk.Tk()
    app = HtmlProcessorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()