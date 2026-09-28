#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scraper pour les pages produit de L'Eau Vive.
Utilise Selenium pour rendre la page (React) puis BeautifulSoup pour extraire.
"""

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False

try:
    import requests
except ImportError:
    requests = None


# ---------- Utilitaires ----------

def clean_text(text: str) -> str:
    if text is None:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


# ---------- Extraction ----------

def extract_title(soup):
    container = soup.select_one("div.page-content div.product-container div.right")
    if not container:
        return ""
    h1 = container.find("h1")
    return clean_text(h1.get_text()) if h1 else ""


def extract_tags(soup):
    """
    Extrait les tags du produit.
    Chaque tag est un span.product-regime-tag. Il peut avoir :
      - un attribut title (ex: "Essentiel bio")
      - un texte visible (ex: "Sans Gluten")
      - ou les deux (ex: title="Essentiel bio", texte="Essentiel Bio")
    """
    tags = []
    tags_container = soup.select_one("div.product-card-tags")
    if not tags_container:
        return tags

    # On ne cible que les spans "racines" portant la classe product-regime-tag
    for span in tags_container.find_all("span", class_="product-regime-tag"):
        title = clean_text(span.get("title", ""))

        # Le texte visible est dans le <span> enfant s'il existe
        inner_span = span.find("span")
        text = clean_text(inner_span.get_text()) if inner_span else clean_text(span.get_text())

        # On ignore les tags complètement vides
        if not title and not text:
            continue

        tags.append({
            "title": title,
            "text": text,
        })

    return tags
def get_accordions(soup):
    accordions = {}
    container = soup.select_one("div.page-content div.product-container div.right div.categories")
    if not container:
        return accordions
    for accordion in container.find_all("div", class_="accordion", recursive=False):
        header = accordion.select_one(".accordion-header .accordion-title")
        content = accordion.select_one(".collapse-css-transition .accordion-content")
        if not header or not content:
            continue
        accordions[clean_text(header.get_text())] = content
    return accordions


def extract_product_info(content):
    result = {"description": "", "reference": ""}
    if content is None:
        return result
    for p in content.find_all("p", recursive=False):
        text = clean_text(p.get_text())
        if not text:
            continue
        m = re.search(r"Référence\s+([A-Za-z0-9_\-]+)", text)
        if m:
            result["reference"] = m.group(1)
        elif not result["description"]:
            result["description"] = text
    if not result["description"]:
        for p in content.find_all("p"):
            text = clean_text(p.get_text())
            if text and not re.search(r"Référence", text):
                result["description"] = text
                break
    return result


def extract_ingredients(content):
    result = {"ingredients": "", "allergenes": ""}
    if content is None:
        return result
    for p in content.find_all("p"):
        text = clean_text(p.get_text())
        if not text:
            continue
        m = re.match(r"Ingrédients\s*:\s*(.+)", text, flags=re.IGNORECASE | re.DOTALL)
        if m and not result["ingredients"]:
            result["ingredients"] = clean_text(m.group(1))
            continue
        m = re.match(r"Allergènes\s*:\s*(.+)", text, flags=re.IGNORECASE | re.DOTALL)
        if m and not result["allergenes"]:
            result["allergenes"] = clean_text(m.group(1))
    return result


def extract_nutrition(content):
    nutrition = {}
    if content is None:
        return nutrition
    for span in content.find_all("span", class_="nutri_data"):
        text = clean_text(span.get_text())
        if not text:
            continue
        if ":" in text:
            label, value = text.split(":", 1)
            nutrition[clean_text(label)] = clean_text(value)
    return nutrition


def parse_product(html_content: str) -> dict:
    soup = BeautifulSoup(html_content, "html.parser")
    title = extract_title(soup)
    tags = extract_tags(soup)
    accordions = get_accordions(soup)

    product_info = extract_product_info(accordions.get("Informations produit"))
    ingredients = extract_ingredients(accordions.get("Ingrédients et allergènes"))
    nutrition = extract_nutrition(accordions.get("Informations nutritionnelles"))

    reference = product_info.get("reference") or "unknown"

    return {
        "reference": reference,
        "title": title,
        "tags": tags,
        "description": product_info.get("description", ""),
        "ingredients": ingredients.get("ingredients", ""),
        "allergenes": ingredients.get("allergenes", ""),
        "nutrition": nutrition,
    }


# ---------- Récupération du contenu ----------

WAIT_SECONDS = 5


def fetch_with_selenium(url: str) -> str:
    """Ouvre la page dans Chrome headless, attend 5s, renvoie le HTML rendu."""
    if not SELENIUM_OK:
        print("Erreur : Selenium / webdriver-manager ne sont pas installés.")
        print("Installez-les avec : pip install selenium webdriver-manager")
        sys.exit(1)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    print("🌐 Ouverture du navigateur headless...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get(url)

        # Attente explicite : on attend que le bloc produit soit présent
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.product-container"))
            )
            print("✅ Bloc produit détecté.")
        except Exception:
            print("⚠️  Bloc produit non détecté dans les 15s, on continue quand même.")

        print(f"⏳ Attente supplémentaire de {WAIT_SECONDS} secondes...")
        time.sleep(WAIT_SECONDS)

        return driver.page_source
    finally:
        driver.quit()


def fetch_content(source: str) -> str:
    source = source.strip().strip('"').strip("'")

    if is_url(source):
        return fetch_with_selenium(source)

    path = Path(source)
    if not path.exists():
        print(f"Erreur : le fichier '{source}' n'existe pas.")
        sys.exit(1)
    print(f"Lecture du fichier local : {path}")
    return path.read_text(encoding="utf-8")


# ---------- Interaction ----------

def ask_source() -> str:
    print("=" * 60)
    print(" Scraper produit - L'Eau Vive")
    print("=" * 60)
    print("Entrez l'URL de la page produit ou le chemin d'un fichier HTML local.")
    print("Exemples :")
    print("  https://www.eau-vive.com/magasin-bio/produit/..._117258")
    print("  ./page_produit.html")
    print()

    while True:
        source = input("Lien de la page à analyser : ").strip()
        if not source:
            print("⚠️  Veuillez saisir une URL ou un chemin de fichier.")
            continue
        if is_url(source) or Path(source).exists():
            return source
        print(f"⚠️  '{source}' n'est ni une URL valide ni un fichier existant.")
        retry = input("Voulez-vous réessayer ? (o/n) : ").strip().lower()
        if retry != "o":
            sys.exit(0)


def main():
    source = ask_source()

    try:
        html_content = fetch_content(source)
    except Exception as e:
        print(f"Erreur lors de la récupération du contenu : {e}")
        sys.exit(1)

    product = parse_product(html_content)
    reference = product["reference"]
    output_path = f"{reference}.json"

    data = {reference: product}
    Path(output_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"✅ JSON écrit dans : {output_path}")
    print()
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()