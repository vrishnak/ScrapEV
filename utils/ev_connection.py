from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

def get_connected_driver(shop_name, headless=True):
    """
    Initialise un driver Selenium, sélectionne le magasin Eau Vive,
    et retourne le driver connecté au contexte de ce magasin.
    
    Args:
        shop_name: Nom du magasin à sélectionner.
        headless: Si True, le navigateur s'exécute en arrière-plan sans fenêtre.
        
    Returns:
        driver: Une instance de webdriver connectée au bon magasin, ou None en cas d'échec.
    """
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-application-cache")

    # Désactiver le chargement des images pour accélérer le chargement
    options.add_experimental_option(
        "prefs",
        {
            "profile.managed_default_content_settings.images": 2
        }
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 15)

    print(f"\n🏪 [CONNEXION] Tentative de sélection du magasin : {shop_name}")
    try:
        shops_url = "https://www.eau-vive.com/magasins"
        driver.get(shops_url)
        time.sleep(3)

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".shop-item")))
        shop_items = driver.find_elements(By.CSS_SELECTOR, ".shop-item")

        shop_found = False
        for item in shop_items:
            try:
                name_element = item.find_element(By.CSS_SELECTOR, ".name")
                shop_name_text = name_element.text.strip()
                if shop_name.strip().lower() == shop_name_text.strip().lower():
                    choose_button = item.find_element(By.CSS_SELECTOR, "button.tertiary-button.orange")
                    driver.execute_script("arguments[0].click();", choose_button)
                    shop_found = True
                    break
            except Exception as e:
                continue
                
        if not shop_found:
            print(f"❌ [CONNEXION] Le magasin '{shop_name}' n'a pas été trouvé sur le site.")
            driver.quit()
            return None

        # Laisser le temps à la sélection d'être enregistrée (cookie / localstorage)
        time.sleep(3)
        print(f"✅ [CONNEXION] Magasin '{shop_name}' sélectionné avec succès.")
        return driver

    except Exception as e:
        print(f"❌ [CONNEXION] Erreur lors de la sélection du magasin : {e}")
        driver.quit()
        return None
