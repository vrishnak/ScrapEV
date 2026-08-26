"""
extract_ean.py
Extraction des données produits depuis les fichiers HTML générés par Capture_MultiSite_ByEAN.py
Version avec interface graphique et sauvegarde JSON
"""

from bs4 import BeautifulSoup
import pandas as pd
import re
import json
import os
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading


class EANExtractorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Extracteur EAN - Analyse des résultats Biocoop")
        self.root.geometry("900x700")

        self.is_running = False
        self.current_thread = None

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)

        # Titre
        title_label = ttk.Label(main_frame, text="Extracteur EAN - Analyse des résultats",
                                font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, pady=10)

        # Frame pour les fichiers
        file_frame = ttk.LabelFrame(main_frame, text="Fichiers à analyser", padding="10")
        file_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=10)
        file_frame.columnconfigure(1, weight=1)

        # Fichier unique ou multiple
        self.extract_type = tk.StringVar(value="single")
        ttk.Radiobutton(file_frame, text="Fichier unique", variable=self.extract_type,
                        value="single").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Radiobutton(file_frame, text="Dossier complet", variable=self.extract_type,
                        value="folder").grid(row=0, column=1, sticky=tk.W, padx=5)

        # Sélection du fichier
        self.file_path_var = tk.StringVar()
        file_entry = ttk.Entry(file_frame, textvariable=self.file_path_var, width=60)
        file_entry.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        file_btn = ttk.Button(file_frame, text="Parcourir", command=self.browse_file)
        file_btn.grid(row=1, column=2, padx=5, pady=5)

        # Dossier de sortie
        ttk.Label(file_frame, text="Dossier de sortie:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.output_dir_var = tk.StringVar(value="DATA/extraction")
        output_entry = ttk.Entry(file_frame, textvariable=self.output_dir_var, width=60)
        output_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5)
        output_btn = ttk.Button(file_frame, text="Parcourir", command=self.browse_output_dir)
        output_btn.grid(row=2, column=2, padx=5, pady=5)

        # Options de sauvegarde
        save_frame = ttk.LabelFrame(main_frame, text="Formats de sortie", padding="10")
        save_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=10)

        self.save_json_var = tk.BooleanVar(value=True)
        self.save_excel_var = tk.BooleanVar(value=True)
        self.save_stats_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(save_frame, text="JSON (données extraites)",
                        variable=self.save_json_var).grid(row=0, column=0, padx=10, sticky=tk.W)
        ttk.Checkbutton(save_frame, text="Excel (données extraites)",
                        variable=self.save_excel_var).grid(row=0, column=1, padx=10, sticky=tk.W)
        ttk.Checkbutton(save_frame, text="Statistiques (rapport)",
                        variable=self.save_stats_var).grid(row=0, column=2, padx=10, sticky=tk.W)

        # Bouton de lancement
        self.start_btn = ttk.Button(main_frame, text="Lancer l'extraction",
                                    command=self.start_extraction, style='Accent.TButton')
        self.start_btn.grid(row=3, column=0, pady=10)

        # Barre de progression
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate', length=400)
        self.progress.grid(row=4, column=0, pady=10, sticky=(tk.W, tk.E))

        # Zone de log
        log_frame = ttk.LabelFrame(main_frame, text="Journal d'activité", padding="10")
        log_frame.grid(row=5, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=100)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configurer le redimensionnement
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

    def browse_file(self):
        """Parcourir pour sélectionner un fichier ou dossier"""
        if self.extract_type.get() == "single":
            filename = filedialog.askopenfilename(
                title="Sélectionner un fichier HTML",
                filetypes=[("HTML files", "*.html"), ("All files", "*.*")]
            )
            if filename:
                self.file_path_var.set(filename)
        else:
            directory = filedialog.askdirectory(
                title="Sélectionner un dossier contenant les fichiers HTML"
            )
            if directory:
                self.file_path_var.set(directory)

    def browse_output_dir(self):
        """Parcourir pour sélectionner le dossier de sortie"""
        directory = filedialog.askdirectory(title="Sélectionner le dossier de sortie")
        if directory:
            self.output_dir_var.set(directory)

    def log(self, message):
        """Ajouter un message au journal"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def start_extraction(self):
        """Démarrer l'extraction"""
        file_path = self.file_path_var.get()
        if not file_path:
            messagebox.showwarning("Avertissement", "Veuillez sélectionner un fichier ou dossier")
            return

        if not os.path.exists(file_path):
            messagebox.showerror("Erreur", f"Le chemin {file_path} n'existe pas")
            return

        if self.is_running:
            messagebox.showinfo("Information", "Une extraction est déjà en cours")
            return

        self.is_running = True
        self.start_btn.config(state='disabled')
        self.progress.start()

        self.log("=" * 50)
        self.log("Début de l'extraction des données")
        self.log(f"Source: {file_path}")
        self.log("=" * 50)

        self.current_thread = threading.Thread(target=self.run_extraction)
        self.current_thread.daemon = True
        self.current_thread.start()

    def run_extraction(self):
        """Exécuter l'extraction"""
        try:
            file_path = self.file_path_var.get()
            output_dir = self.output_dir_var.get()

            # Créer le dossier de sortie
            os.makedirs(output_dir, exist_ok=True)

            # Extraire selon le type
            if self.extract_type.get() == "single":
                self.extract_single_file(file_path, output_dir)
            else:
                self.extract_multiple_files(file_path, output_dir)

            self.log("\n" + "=" * 50)
            self.log("✅ Extraction terminée avec succès!")
            self.log("=" * 50)

            messagebox.showinfo("Succès",
                                f"Extraction terminée!\n\nLes fichiers ont été sauvegardés dans:\n{output_dir}")

        except Exception as e:
            self.log(f"\n✗ Erreur fatale: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
            messagebox.showerror("Erreur", f"Une erreur est survenue: {str(e)}")
        finally:
            self.is_running = False
            self.start_btn.config(state='normal')
            self.progress.stop()

    def extract_single_file(self, html_file_path, output_dir):
        """Extraire les données d'un seul fichier"""
        self.log(f"Traitement du fichier: {html_file_path}")

        # Extraire les données
        df = self.extract_ean_from_html(html_file_path)

        if df.empty:
            self.log("⚠️ Aucune donnée extraite du fichier")
            return

        self.log(f"✅ {len(df)} magasins extraits")

        # Analyser les ruptures
        stats = self.analyser_ruptures(df)

        # Afficher le résumé
        self.log(f"\n📊 RÉSUMÉ:")
        self.log(f"   Produit EAN: {stats['ean']}")
        self.log(f"   Total magasins: {stats['total_magasins']}")
        self.log(f"   En rupture: {stats['magasins_en_rupture']} ({stats['taux_rupture']:.1f}%)")
        self.log(f"   Disponibles: {stats['magasins_disponibles']}")
        if stats['prix_moyen']:
            self.log(f"   Prix moyen: {stats['prix_moyen']:.2f} €")

        # Sauvegarder les résultats
        self.sauvegarder_resultats(df, stats, output_dir)

    def extract_multiple_files(self, folder_path, output_dir):
        """Extraire les données de plusieurs fichiers"""
        html_files = list(Path(folder_path).glob("*.html"))

        if not html_files:
            self.log(f"⚠️ Aucun fichier HTML trouvé dans {folder_path}")
            return

        self.log(f"🔍 {len(html_files)} fichiers HTML trouvés")

        all_results = []
        processed = 0

        for html_file in html_files:
            if not self.is_running:
                break

            self.log(f"\nTraitement: {html_file.name}")
            try:
                df = self.extract_ean_from_html(str(html_file))
                if not df.empty:
                    stats = self.analyser_ruptures(df)
                    all_results.append(stats)
                    processed += 1
                    self.log(f"  ✓ {len(df)} magasins extraits")
            except Exception as e:
                self.log(f"  ✗ Erreur: {str(e)}")

        self.log(f"\n✅ {processed}/{len(html_files)} fichiers traités avec succès")

        # Créer un récapitulatif global
        if all_results:
            recap_df = pd.DataFrame(all_results)
            recap_file = os.path.join(output_dir, "recapitulatif_global.xlsx")
            recap_df.to_excel(recap_file, index=False)
            self.log(f"📊 Récapitulatif global sauvegardé: {recap_file}")

    def extract_ean_from_html(self, html_file_path):
        """Extrait les données des produits depuis un fichier HTML"""
        with open(html_file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')

        # Extraction du numéro EAN
        product_number_div = soup.find('div', class_='product-number')
        ean = product_number_div.get_text(strip=True) if product_number_div else "Non trouvé"

        products_data = []
        result_items = soup.find_all('div', class_='result-item')

        for item in result_items:
            magasin_header = item.find('div', class_='magasin-header')
            if not magasin_header:
                continue

            # Nom du magasin
            magasin_h2 = magasin_header.find('h2')
            magasin = magasin_h2.get_text(strip=True).replace('🏪', '').strip() if magasin_h2 else "Inconnu"

            # Adresse et URL
            addresses = magasin_header.find_all('div', class_='magasin-address')
            adresse = addresses[0].get_text(strip=True).replace('📍', '').strip() if len(addresses) > 0 else "Inconnue"
            url_magasin = addresses[1].get_text(strip=True).replace('🔗', '').strip() if len(
                addresses) > 1 else "Inconnue"

            # Extraction des données produit
            product_content = item.find('div', class_='product-content')
            if not product_content:
                continue

            # Détection des ruptures
            out_of_stock_span = product_content.find('span', class_='out-of-stock')
            is_rupture = out_of_stock_span is not None and "rupture" in out_of_stock_span.get_text().lower()

            # Extraction du prix
            prix_final = None
            if not is_rupture:
                price_wrapper = product_content.find('span', class_='price-wrapper')
                if price_wrapper and price_wrapper.get('data-price-amount'):
                    prix_final = float(price_wrapper.get('data-price-amount'))
                else:
                    price_span = product_content.find('span', class_='price')
                    if price_span:
                        price_text = price_span.get_text(strip=True)
                        match = re.search(r'([\d,]+)\s*€', price_text)
                        if match:
                            prix_final = float(match.group(1).replace(',', '.'))

            # Extraction du prix au kg
            prix_au_kg = None
            weight_price_div = product_content.find('div', class_='weight-price')
            if weight_price_div:
                weight_price_text = weight_price_div.get_text(strip=True)
                match = re.search(r'([\d,]+)\s*€', weight_price_text)
                if match:
                    prix_au_kg = float(match.group(1).replace(',', '.'))

            # Extraction du conditionnement
            conditionnement = None
            part_product_div = product_content.find('div', class_='part-product')
            if part_product_div:
                conditionnement = part_product_div.get_text(strip=True)

            if not conditionnement:
                conditionnement = "Non spécifié"

            # Nom du produit
            product_name = "Non spécifié"
            name_span = product_content.find('span', itemprop='name')
            if name_span:
                product_name = name_span.get_text(strip=True)

            # Marque
            marque = "Non spécifiée"
            brand_span = product_content.find('span', class_='brand value')
            if brand_span:
                marque = brand_span.get_text(strip=True)

            product_entry = {
                'ean': ean,
                'magasin': magasin,
                'adresse': adresse,
                'url_magasin': url_magasin,
                'produit': product_name,
                'marque': marque,
                'prix_final': "RUPTURE" if is_rupture else (prix_final if prix_final else None),
                'prix_au_kg': prix_au_kg,
                'conditionnement': conditionnement,
                'disponibilite': 'Rupture' if is_rupture else ('En stock' if prix_final else 'Indéterminé')
            }

            products_data.append(product_entry)

        return pd.DataFrame(products_data)

    def analyser_ruptures(self, df):
        """Analyse les ruptures de stock"""
        if df.empty:
            return {"erreur": "Aucune donnée à analyser"}

        total_magasins = len(df)
        magasins_rupture = len(df[df['disponibilite'] == 'Rupture'])
        magasins_disponibles = len(df[df['disponibilite'] == 'En stock'])

        # Prix moyen
        prix_moyen = None
        if magasins_disponibles > 0:
            prix_disponibles = df[df['disponibilite'] == 'En stock']['prix_final']
            prix_disponibles = prix_disponibles[prix_disponibles.notna()]
            if len(prix_disponibles) > 0:
                prix_moyen = prix_disponibles.mean()

        # Prix au kg moyen
        prix_au_kg_moyen = df['prix_au_kg'].mean() if 'prix_au_kg' in df.columns else None

        # Liste des magasins en rupture
        magasins_rupture_list = df[df['disponibilite'] == 'Rupture']['magasin'].tolist()

        return {
            "ean": df['ean'].iloc[0] if not df.empty else None,
            "total_magasins": total_magasins,
            "magasins_en_rupture": magasins_rupture,
            "magasins_disponibles": magasins_disponibles,
            "taux_rupture": (magasins_rupture / total_magasins * 100) if total_magasins > 0 else 0,
            "prix_moyen": prix_moyen,
            "prix_au_kg_moyen": prix_au_kg_moyen,
            "magasins_rupture_list": magasins_rupture_list,
            "prix_min": df[df['disponibilite'] == 'En stock']['prix_final'].min() if magasins_disponibles > 0 else None,
            "prix_max": df[df['disponibilite'] == 'En stock']['prix_final'].max() if magasins_disponibles > 0 else None
        }

    def sauvegarder_resultats(self, df, stats, output_dir):
        """Sauvegarde les résultats dans différents formats"""
        ean = stats.get('ean', 'inconnu')
        timestamp = datetime.now().strftime("%y%m%d_%H%M%S")

        saved_files = []

        # Sauvegarder en Excel
        if self.save_excel_var.get():
            excel_file = os.path.join(output_dir, f"extraction_{ean}_{timestamp}.xlsx")
            df.to_excel(excel_file, index=False)
            self.log(f"✅ Excel sauvegardé: {excel_file}")
            saved_files.append(excel_file)

        # Sauvegarder en JSON
        if self.save_json_var.get():
            json_file = os.path.join(output_dir, f"extraction_{ean}_{timestamp}.json")
            df.to_json(json_file, orient='records', force_ascii=False, indent=4)
            self.log(f"✅ JSON sauvegardé: {json_file}")
            saved_files.append(json_file)

        # Sauvegarder les statistiques
        if self.save_stats_var.get():
            stats_file = os.path.join(output_dir, f"statistiques_{ean}_{timestamp}.json")
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=4, default=str)
            self.log(f"✅ Statistiques sauvegardées: {stats_file}")
            saved_files.append(stats_file)

        return saved_files


def main():
    root = tk.Tk()
    app = EANExtractorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()