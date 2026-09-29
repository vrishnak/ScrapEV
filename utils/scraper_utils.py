import os
import time
import json
import re
import unicodedata
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from utils.ev_connection import get_connected_driver
from utils.parser_utils import get_last_page_number, parse_products_from_html

class ScraperV6:
    """
    Classe reprenant la logique de scraping de TestScrapV5 mais adaptée 
    pour interagir avec une interface graphique (GUI) via des callbacks de logs.
    """
    def __init__(self, driver, base_url, log_callback=print):
        self.driver = driver
        self.base_url = base_url
        self.wait = WebDriverWait(self.driver, 15)
        self.all_products = []
        # log_callback permet d'envoyer les messages vers la zone de texte de l'interface
        self.log = log_callback 

    def wait_for_page_load(self, page_num):
        """Attend le chargement des cartes produits."""
        self.log(f"⏳ Attente du chargement de la page {page_num}...")
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.cards-container"))
            )
            time.sleep(2) # Laisser React terminer son rendu
            return True
        except TimeoutException:
            self.log(f"⚠️ Aucun div.cards-container trouvé sur la page {page_num}")
            return False

    def scrape_page(self, page_num):
        """Scrape une page spécifique de la catégorie."""
        url = f"{self.base_url}?page={page_num}" if "?" not in self.base_url else f"{self.base_url}&page={page_num}"
        self.log(f"🌐 Accès à : {url}")
        
        try:
            self.driver.get(url)
            if not self.wait_for_page_load(page_num):
                return False
            
            html_content = self.driver.page_source
            products = parse_products_from_html(html_content)
            self.log(f"📦 {len(products)} produits extraits sur la page {page_num}")
            self.all_products.extend(products)
            return True
        except Exception as e:
            self.log(f"❌ Erreur lors du scraping de la page {page_num} : {e}")
            return False

    def run(self):
        """Lance le scraping de toutes les pages de la catégorie."""
        self.log(f"🚀 Démarrage du scraping : {self.base_url}")
        self.driver.get(self.base_url)
        time.sleep(3)

        if not self.wait_for_page_load(1):
            self.log("❌ Impossible de charger la première page")
            return False
            
        html_content = self.driver.page_source
        last_page = get_last_page_number(html_content)
        
        self.log(f"📚 Dernière page détectée : {last_page}")
        
        for page_num in range(1, last_page + 1):
            self.scrape_page(page_num)
            if page_num < last_page:
                self.log("⏳ Pause avant la page suivante...")
                time.sleep(2)
                
        return True

    def save_data(self, nom_famille, magasin, save_json=True, save_excel=True, dir_json="DATA_EV/JSON", dir_excel="DATA_EV/XLSX"):
        """Sauvegarde les données extraites selon les préférences."""
        if not self.all_products:
            self.log("❌ Aucune donnée à sauvegarder")
            return False
            
        date_folder = datetime.now().strftime("%Y-%m-%d")
        date_str = datetime.now().strftime("%y%m%d")
        
        famille_clean = nettoyer_nom_fichier(nom_famille)
        magasin_clean = nettoyer_nom_fichier(magasin)
        base_name = f"V6_{magasin_clean}_{date_str}_{famille_clean}"

        if save_json:
            # Créer le répertoire pour ce jour dans le dossier JSON de base
            json_dir_today = os.path.join(dir_json, date_folder)
            os.makedirs(json_dir_today, exist_ok=True)
            
            json_path = os.path.join(json_dir_today, f"{base_name}.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(self.all_products, f, ensure_ascii=False, indent=4)
            self.log(f"✅ Fichier JSON sauvegardé : {json_path}")

        if save_excel:
            # Créer le répertoire pour ce jour dans le dossier Excel de base
            excel_dir_today = os.path.join(dir_excel, date_folder)
            os.makedirs(excel_dir_today, exist_ok=True)
            
            excel_path = os.path.join(excel_dir_today, f"{base_name}.xlsx")
            df = pd.DataFrame(self.all_products)
            df.to_excel(excel_path, index=False)
            self.log(f"✅ Fichier Excel sauvegardé : {excel_path}")
            
        return True

# ==============================================================
# OUTILS
# ==============================================================

def nettoyer_nom_fichier(nom):
    """
    Nettoie un nom de famille pour pouvoir l'utiliser dans un nom de fichier Windows.
    """
    nom = unicodedata.normalize("NFD", nom)
    nom = "".join(c for c in nom if unicodedata.category(c) != "Mn")
    nom = nom.replace(" ", "_")
    nom = re.sub(r'[<>:"/\\|?*]', "_", nom)
    return nom

def charger_json(chemin, log_callback=print):
    """
    Charge de manière sécurisée un fichier JSON.
    """
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception as e:
        log_callback(f"❌ Erreur lors du chargement de {chemin} : {e}")
        return None
