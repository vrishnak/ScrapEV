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
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from utils.ev_connection import get_connected_driver
from utils.parser_utils import get_last_page_number, parse_products_from_html

class TestScrapV5:
    def __init__(self, driver, base_url):
        self.driver = driver
        self.base_url = base_url
        self.wait = WebDriverWait(self.driver, 15)
        self.all_products = []

    def wait_for_page_load(self, page_num):
        """Attend le chargement des cartes produits."""
        print(f"⏳ Attente du chargement de la page {page_num}...")
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.cards-container"))
            )
            time.sleep(2) # Laisser React terminer son rendu
            return True
        except TimeoutException:
            print(f"⚠️ Aucun div.cards-container trouvé sur la page {page_num}")
            return False

    def scrape_page(self, page_num):
        url = f"{self.base_url}?page={page_num}" if "?" not in self.base_url else f"{self.base_url}&page={page_num}"
        print(f"🌐 Accès à : {url}")
        
        try:
            self.driver.get(url)
            if not self.wait_for_page_load(page_num):
                return False
            
            html_content = self.driver.page_source
            products = parse_products_from_html(html_content)
            print(f"📦 {len(products)} produits extraits sur la page {page_num}")
            self.all_products.extend(products)
            return True
        except Exception as e:
            print(f"❌ Erreur lors du scraping de la page {page_num} : {e}")
            return False

    def run(self):
        print(f"🚀 Démarrage du scraping : {self.base_url}")
        self.driver.get(self.base_url)
        time.sleep(3)

        if not self.wait_for_page_load(1):
            print("❌ Impossible de charger la première page")
            return False
            
        html_content = self.driver.page_source
        last_page = get_last_page_number(html_content)
        
        print(f"📚 Dernière page détectée : {last_page}")
        
        for page_num in range(1, last_page + 1):
            self.scrape_page(page_num)
            if page_num < last_page:
                print("⏳ Pause avant la page suivante...")
                time.sleep(2)
                
        return True

    def save_data(self, nom_famille, magasin):
        if not self.all_products:
            print("❌ Aucune donnée à sauvegarder")
            return False
            
        date_str = datetime.now().strftime("%y%m%d")
        output_dir = "DATA_EV"
        os.makedirs(output_dir, exist_ok=True)
        
        famille_clean = nettoyer_nom_fichier(nom_famille)
        magasin_clean = nettoyer_nom_fichier(magasin)
        base_name = f"V5_{magasin_clean}_{date_str}_{famille_clean}"
        
        # Save JSON
        json_path = os.path.join(output_dir, f"{base_name}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.all_products, f, ensure_ascii=False, indent=4)
        print(f"✅ Fichier JSON sauvegardé : {json_path}")
        
        # Save Excel
        excel_path = os.path.join(output_dir, f"{base_name}.xlsx")
        df = pd.DataFrame(self.all_products)
        df.to_excel(excel_path, index=False)
        print(f"✅ Fichier Excel sauvegardé : {excel_path}")
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

# ==============================================================
# CHARGEMENT DES MAGASINS
# ==============================================================

def charger_magasins():
    json_path = os.path.join("EAUVIVE_Liste", "EauVive_Liste.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            magasins = json.load(f)
    except Exception as e:
        print(f"❌ Erreur lors du chargement de {json_path} : {e}")
        return None

    if not isinstance(magasins, list):
        print("❌ Le fichier JSON des magasins doit contenir une liste.")
        return None

    magasins_valides = []
    for magasin in magasins:
        if not isinstance(magasin, dict):
            continue
        denomination = magasin.get("denomination")
        if denomination is None:
            continue
        denomination = str(denomination).strip()
        if not denomination:
            continue
        magasins_valides.append(magasin)

    return magasins_valides

# ==============================================================
# SELECTION MULTIPLE MAGASINS
# ==============================================================

def selectionner_magasins():
    magasins = charger_magasins()
    if magasins is None or not magasins:
        print("❌ Aucun magasin disponible.")
        return None

    print("\n" + "=" * 70)
    print("🏪 MAGASINS DISPONIBLES")
    print("=" * 70)

    for index, magasin in enumerate(magasins):
        denomination = magasin.get("denomination", "")
        ville = magasin.get("ville")
        code_postal = magasin.get("code_postal")

        infos = []
        if code_postal: infos.append(str(code_postal))
        if ville: infos.append(str(ville))
        
        suffixe = " - " + " ".join(infos) if infos else ""
        print(f"  [{index}] {denomination}{suffixe}")

    print("  [-1] Tous les magasins")
    print("=" * 70)

    while True:
        choix = input("\n👉 Sélectionnez un ou plusieurs magasins (ex: 2 ou 0;3;5 ou -1) : ").strip()
        
        if choix == "-1":
            print("\n✅ Tous les magasins sélectionnés.")
            return [str(m["denomination"]).strip() for m in magasins]

        if not choix:
            print("❌ Aucune sélection.")
            continue

        morceaux = choix.split(";")
        indices = []
        erreur = False

        for morceau in morceaux:
            morceau = morceau.strip()
            if not morceau:
                print("❌ Format invalide. Utilisez par exemple : 1;3;5")
                erreur = True
                break
            try:
                index = int(morceau)
            except ValueError:
                print(f"❌ '{morceau}' n'est pas un numéro valide.")
                erreur = True
                break

            if not 0 <= index < len(magasins):
                print(f"❌ Le numéro {index} est invalide. Les numéros vont de 0 à {len(magasins) - 1}.")
                erreur = True
                break

            if index not in indices:
                indices.append(index)

        if erreur:
            continue

        if not indices:
            print("❌ Aucun magasin sélectionné.")
            continue

        noms_magasins = [str(magasins[i]["denomination"]).strip() for i in indices]
        
        print("\n✅ Magasins sélectionnés :")
        for nom in noms_magasins:
            print(f"   - {nom}")

        return noms_magasins

# ==============================================================
# CHARGEMENT DES FAMILLES
# ==============================================================

def charger_familles():
    json_path = os.path.join("EAUVIVE_Liste", "EauVive_URL_Famille.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            familles = json.load(f)
    except Exception as e:
        print(f"❌ Erreur lors du chargement de {json_path} : {e}")
        return None

    if not isinstance(familles, list):
        print("❌ Le fichier des familles doit contenir une liste.")
        return None

    return familles

# ==============================================================
# SELECTION DES FAMILLES
# ==============================================================

def selectionner_familles(familles):
    print("\n" + "=" * 70)
    print("📋 FAMILLES DISPONIBLES")
    print("=" * 70)

    for index, item in enumerate(familles):
        nom = item.get("Famille", f"Famille {index}")
        print(f"  [{index}] {nom}")

    print("  [-1] Toutes les familles")
    print("=" * 70)

    while True:
        choix = input("\n👉 Sélectionnez une ou plusieurs familles (ex: 2 ou 1;3;5 ou -1) : ").strip()

        if choix == "-1":
            print("\n✅ Toutes les familles sélectionnées.")
            return list(range(len(familles)))

        if not choix:
            print("❌ Aucune sélection.")
            continue

        morceaux = choix.split(";")
        indices = []
        erreur = False

        for morceau in morceaux:
            morceau = morceau.strip()
            if not morceau:
                print("❌ Format invalide. Utilisez par exemple : 1;3;5")
                erreur = True
                break
            try:
                index = int(morceau)
            except ValueError:
                print(f"❌ '{morceau}' n'est pas un numéro valide.")
                erreur = True
                break

            if not 0 <= index < len(familles):
                print(f"❌ Le numéro {index} est invalide. Les numéros vont de 0 à {len(familles) - 1}.")
                erreur = True
                break

            if index not in indices:
                indices.append(index)

        if erreur:
            continue

        if not indices:
            print("❌ Aucune famille sélectionnée.")
            continue

        print("\n✅ Familles sélectionnées :")
        for index in indices:
            print(f"   [{index}] {familles[index].get('Famille', '')}")

        return indices

# ==============================================================
# SCRAPING D'UNE FAMILLE
# ==============================================================

def scraper_famille_v5(driver, famille, magasin):
    URL = famille.get("lien")
    nom_famille = famille.get("Famille", "Famille")

    if not URL:
        print(f"❌ Aucun lien trouvé pour la famille '{nom_famille}'")
        return

    print("\n" + "=" * 70)
    print(f"🚀 SCRAPING : {nom_famille}")
    print(f"📌 URL : {URL}")
    print("=" * 70)

    scraper = TestScrapV5(driver, URL)

    try:
        if scraper.run():
            if scraper.save_data(nom_famille, magasin):
                print(f"✅ Famille '{nom_famille}' terminée.")
            else:
                print(f"❌ Échec de la sauvegarde de '{nom_famille}'.")
        else:
            print(f"❌ Le scraping a échoué pour '{nom_famille}'.")
    except Exception as e:
        print(f"❌ Erreur inattendue pour '{nom_famille}' : {e}")

# ==============================================================
# PROGRAMME PRINCIPAL
# ==============================================================

if __name__ == "__main__":
    # ⚙️ CONFIGURATION
    HEADLESS_MODE = True  # Mettre à False pour afficher la fenêtre Chrome

    print("\n" + "=" * 70)
    print("🌿 EAUVIVE - SCRAPER V5 MULTI-MAGASIN")
    print("=" * 70)

    # 1. SELECTION DES MAGASINS
    magasins_choisis = selectionner_magasins()
    if not magasins_choisis:
        exit(1)

    # 2. CHARGEMENT DES FAMILLES
    familles = charger_familles()
    if familles is None or not familles:
        print("❌ Aucune famille disponible.")
        exit(1)

    # 3. SELECTION DES FAMILLES
    indices_familles = selectionner_familles(familles)

    # 4. CONFIRMATION
    print("\n" + "=" * 70)
    print("📋 RÉCAPITULATIF")
    print("=" * 70)
    
    print(f"🏪 Nombre de magasins : {len(magasins_choisis)}")
    for m in magasins_choisis:
        print(f"   - {m}")

    print(f"\n📦 Nombre de familles par magasin : {len(indices_familles)}")
    for index in indices_familles:
        print(f"   [{index}] {familles[index].get('Famille', '')}")

    print(f"\n💾 Destination : {os.path.abspath('DATA_EV')}")
    print("=" * 70)

    confirmation = input("\n👉 Lancer le scraping ? (o/n) : ").strip().lower()
    if confirmation not in ("o", "oui"):
        print("❌ Scraping annulé.")
        exit(0)

    # 5. SCRAPING
    for index_magasin, magasin in enumerate(magasins_choisis):
        print("\n" + "=" * 70)
        print(f"🛒 TRAITEMENT DU MAGASIN [{index_magasin + 1}/{len(magasins_choisis)}] : {magasin}")
        print("=" * 70)

        # On initialise un driver connecté pour CE magasin
        driver = get_connected_driver(magasin, headless=HEADLESS_MODE)

        if not driver:
            print(f"⚠️ Impossible de se connecter au magasin {magasin}. Passage au suivant.")
            continue

        for i, index_famille in enumerate(indices_familles):
            famille = familles[index_famille]
            
            scraper_famille_v5(driver, famille, magasin)

            if i != len(indices_familles) - 1:
                print("\n⏳ Pause avant la famille suivante...")
                time.sleep(2)

        print(f"\n🔒 Fermeture de la connexion pour {magasin}")
        driver.quit()

    print("\n" + "=" * 70)
    print("🎉 TRAITEMENT GLOBAL TERMINÉ")
    print("=" * 70)

