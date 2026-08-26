import time
import os
import json
import re
import unicodedata
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from utils.ev_connection import get_connected_driver

class WebScraper:
    def __init__(self, driver, url, shop_name=None):
        """
        Initialise le scraper avec un driver déjà connecté et l'URL de base.

        Args:
            driver: Instance WebDriver déjà initialisée et connectée au magasin
            url: URL de la famille à scraper
            shop_name: Nom du magasin
        """
        self.driver = driver
        self.base_url = url
        self.shop_name = shop_name
        self.wait = WebDriverWait(self.driver, 15)
        self.all_html = []

    # ==========================================================
    # PAGINATION
    # ==========================================================

    def get_last_page_number(self):
        """
        Récupère le numéro de la dernière page depuis la pagination.
        """
        try:
            pagination = self.driver.find_element(
                By.CSS_SELECTOR,
                "ul.pagination.products"
            )
            links = pagination.find_elements(
                By.TAG_NAME,
                "a"
            )
            if len(links) >= 2:
                last_page_link = links[-2]
                last_page_number = int(last_page_link.text.strip())
                print(f"📄 Dernière page détectée : {last_page_number}")
                return last_page_number
            print("⚠️ Pas assez de liens dans la pagination.")
            return 1
        except (NoSuchElementException, ValueError, IndexError) as e:
            print(f"⚠️ Erreur de détection de la pagination : {e}")
            return 1

    # ==========================================================
    # ATTENTE CHARGEMENT
    # ==========================================================

    def wait_for_page_load(self, page_num):
        """
        Attend le chargement des cartes produits.
        """
        print(f"⏳ Attente du chargement de la page {page_num}...")
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.cards-container"))
            )
            print(f"✅ div.cards-container trouvé sur la page {page_num}")
        except TimeoutException:
            print(f"⚠️ Aucun div.cards-container trouvé sur la page {page_num}")
            time.sleep(3)

        # Laisser React terminer son rendu
        time.sleep(2)
        containers = self.driver.find_elements(By.CSS_SELECTOR, "div.cards-container")

        if containers:
            cards = containers[0].find_elements(By.CSS_SELECTOR, ".card-container")
            print(f"✅ Page {page_num} chargée avec {len(cards)} cartes")
            return True

        print(f"⚠️ Page {page_num} sans conteneurs")
        return False

    # ==========================================================
    # SCRAP PAGE
    # ==========================================================

    def scrape_page(self, page_num):
        """
        Scrape une page spécifique.
        """
        if "?" in self.base_url:
            url = f"{self.base_url}&page={page_num}"
        else:
            url = f"{self.base_url}?page={page_num}"

        print(f"🌐 Accès à : {url}")
        try:
            self.driver.get(url)
            if not self.wait_for_page_load(page_num):
                return False

            containers = self.driver.find_elements(By.CSS_SELECTOR, "div.cards-container")
            if not containers:
                print(f"⚠️ Aucun conteneur trouvé sur la page {page_num}")
                return False

            print(f"📦 Récupération de {len(containers)} conteneur(s)")
            for container in containers:
                container_html = container.get_attribute("outerHTML")
                self.all_html.append(container_html)

            print(f"✅ Page {page_num} traitée avec succès")
            return True
        except Exception as e:
            print(f"❌ Erreur lors du scraping de la page {page_num} : {e}")
            return False

    # ==========================================================
    # SCRAPE TOUTES LES PAGES
    # ==========================================================

    def scrape_all_pages(self):
        """
        Scrape toutes les pages disponibles.
        """
        print(f"🚀 Démarrage du scraping : {self.base_url}")
        
        # Le magasin est déjà sélectionné grâce au driver passé en paramètre
        # On va directement sur la page
        self.driver.get(self.base_url)
        time.sleep(3)

        # Vérification de la première page
        if not self.wait_for_page_load(1):
            print("❌ Impossible de charger la première page")
            return False

        # Nombre de pages
        last_page = self.get_last_page_number()

        # Scraping
        if last_page == 1:
            print("📄 Une seule page détectée")
            self.scrape_page(1)
        else:
            print(f"📚 Scraping de {last_page} pages au total")
            for page_num in range(1, last_page + 1):
                self.scrape_page(page_num)
                if page_num < last_page:
                    time.sleep(2)

        print(f"✅ Scraping de la famille terminé ! {len(self.all_html)} conteneur(s) récupéré(s)")
        return True

    # ==========================================================
    # SAUVEGARDE HTML
    # ==========================================================

    def save_to_html(self, filename=None):
        """
        Sauvegarde tous les conteneurs HTML.
        Les fichiers sont sauvegardés dans : DATA_EV/HTML
        """
        if not self.all_html:
            print("❌ Aucune donnée à sauvegarder")
            return False

        output_dir = os.path.join("DATA_EV", "HTML")
        os.makedirs(output_dir, exist_ok=True)

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"scraped_data_{timestamp}.html"

        if not filename.lower().endswith(".html"):
            filename += ".html"

        filepath = os.path.join(output_dir, filename)
        print(f"💾 Sauvegarde dans : {filepath}")

        html_content = "\n".join(self.all_html)

        if '<div class="cards-container"' in html_content:
            cards_count = html_content.count("card-container")
            print(f"✅ {cards_count} cartes trouvées dans le contenu")
        else:
            print("⚠️ ATTENTION : Aucune balise div.cards-container trouvée")

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"✅ Fichier sauvegardé : {os.path.abspath(filepath)}")
            print(f"📊 Taille : {os.path.getsize(filepath)} octets")
            return True
        except Exception as e:
            print(f"❌ Erreur lors de la sauvegarde : {e}")
            return False


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
# SELECTION MULTIPLE MAGASINS (NOUVEAU)
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

def scraper_famille(driver, famille, magasin, date_du_jour):
    URL = famille.get("lien")
    nom_famille = famille.get("Famille", "Famille")

    if not URL:
        print(f"❌ Aucun lien trouvé pour la famille '{nom_famille}'")
        return

    print("\n" + "=" * 70)
    print(f"🚀 SCRAPING : {nom_famille}")
    print(f"📌 URL : {URL}")
    print("=" * 70)

    nom_famille_fichier = nettoyer_nom_fichier(nom_famille)
    magasin_fichier = nettoyer_nom_fichier(magasin)
    nom_fichier = f"GRAB-{magasin_fichier}-{date_du_jour}-{nom_famille_fichier}.html"

    # On utilise le WebScraper modifié avec le driver existant
    scraper = WebScraper(driver, URL, shop_name=magasin)

    try:
        if scraper.scrape_all_pages():
            if scraper.save_to_html(nom_fichier):
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
    print("🌿 EAUVIVE - SCRAPER MULTI-MAGASIN V4")
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

    print(f"\n💾 Destination : {os.path.abspath(os.path.join('DATA_EV', 'HTML'))}")
    print("=" * 70)

    confirmation = input("\n👉 Lancer le scraping ? (o/n) : ").strip().lower()
    if confirmation not in ("o", "oui"):
        print("❌ Scraping annulé.")
        exit(0)

    # 5. SCRAPING
    date_du_jour = datetime.now().strftime("%Y%m%d")

    # On boucle sur chaque magasin choisi
    for index_magasin, magasin in enumerate(magasins_choisis):
        print("\n" + "=" * 70)
        print(f"🛒 TRAITEMENT DU MAGASIN [{index_magasin + 1}/{len(magasins_choisis)}] : {magasin}")
        print("=" * 70)

        # On initialise un driver connecté pour CE magasin
        driver = get_connected_driver(magasin, headless=HEADLESS_MODE)

        if not driver:
            print(f"⚠️ Impossible de se connecter au magasin {magasin}. Passage au suivant.")
            continue

        # On boucle sur chaque famille pour ce magasin
        for i, index_famille in enumerate(indices_familles):
            famille = familles[index_famille]
            
            scraper_famille(driver, famille, magasin, date_du_jour)

            # Petite pause entre deux familles
            if i != len(indices_familles) - 1:
                print("\n⏳ Pause avant la famille suivante...")
                time.sleep(2)

        # Une fois toutes les familles faites pour ce magasin, on ferme le navigateur
        print(f"\n🔒 Fermeture de la connexion pour {magasin}")
        driver.quit()

    # FIN
    print("\n" + "=" * 70)
    print("🎉 TRAITEMENT GLOBAL TERMINÉ")
    print("=" * 70)
