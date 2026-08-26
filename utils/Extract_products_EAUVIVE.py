from bs4 import BeautifulSoup
import pandas as pd
import re


def extract_products_eauvive(html_content):
    """
    Analyse le code HTML fourni en paramètre et extrait les informations des produits.
    Cette fonction parcourt tous les éléments de classe "product-card" pour récupérer :
    - Identifiants, URL, nom
    - Poids/volume, prix, prix au kilo
    - Tags (sans gluten, sans lactose, etc.)
    - EAN (extrait de l'URL de l'image si disponible)

    Args:
        html_content (str): Le code HTML source d'une page produit/catégorie.

    Returns:
        pd.DataFrame: Un DataFrame pandas contenant une ligne par produit avec toutes ses caractéristiques.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    products = []

    # Itération sur chaque bloc produit
    for card in soup.select("div.product-card"):
        product = {}

        # --- 1. Extraction du nom depuis le div.product-title ---
        title_div = card.select_one("div.product-title")
        if title_div:
            title_link = title_div.select_one("a")
            if title_link:
                product["name"] = title_link.get_text(strip=True)
                product["url"] = title_link.get("href")

                # Extraction du numéro de référence interne depuis l'URL
                # Format: /magasin-bio/produit/nom-produit_XXXXX
                ref_match = re.search(r'_(\d+)$', product["url"]) if product["url"] else None
                product["ref_id"] = ref_match.group(1) if ref_match else None

        # --- 2. Extraction depuis l'image (a.img-link) ---
        img_link = card.select_one("a.img-link")
        if img_link:
            img_tag = img_link.select_one("img")
            if img_tag:
                img_src = img_tag.get("src") or img_tag.get("data-src")
                product["img_url"] = img_src
                product["img_alt"] = img_tag.get("alt")

                # --- Traitement de l'URL de l'image pour extraire l'EAN ---
                # Format typique: .../[CODE]-[EAN]-[MARQUE]-[DESCRIPTION].jpg
                # EAN = 13 chiffres, en 2ème position
                if img_src:
                    filename = img_src.split("/")[-1]
                    name_stem = filename.rsplit(".", 1)[0]
                    parts = name_stem.split("-")

                    product["ean"] = None
                    if len(parts) >= 2:
                        # Vérifier que c'est bien un EAN de 13 chiffres
                        potential_ean = parts[1]
                        if re.match(r'^\d{13}$', potential_ean):
                            product["ean"] = potential_ean
                        # Fallback: chercher un EAN n'importe où dans le nom
                        else:
                            ean_match = re.search(r'\b(\d{13})\b', name_stem)
                            if ean_match:
                                product["ean"] = ean_match.group(1)

        # --- 3. Extraction du prix ---
        price_span = card.select_one("span.product-price")
        if price_span:
            price_text = price_span.get_text(strip=True).replace("€", "").replace(",", ".")
            try:
                product["price"] = float(price_text)
            except ValueError:
                product["price"] = None

        # Prix barré (promotion)
        price_old_span = card.select_one("span.product-not-price")
        if price_old_span:
            price_old_text = price_old_span.get_text(strip=True).replace("€", "").replace(",", ".")
            try:
                product["price_old"] = float(price_old_text)
            except ValueError:
                product["price_old"] = None

        # --- 4. Extraction du volume/poids et prix unitaire ---
        price_types = card.select("span.product-price-type")
        if len(price_types) >= 1:
            product["volume"] = price_types[0].get_text(strip=True)
        if len(price_types) >= 2:
            product["price_unit"] = price_types[1].get_text(strip=True)

        # --- 5. Extraction des tags / labels ---
        tags = []
        for tag in card.select("span.product-regime-tag"):
            tag_text = tag.get_text(strip=True)
            if tag_text:
                tags.append(tag_text)
        product["tags"] = tags

        # --- 6. Badge promotion ---
        promo_badge = card.select_one("div.promotion-badge")
        product["is_promo"] = promo_badge is not None

        # --- 7. Ajout d'informations supplémentaires ---
        # Marque (peut être déduite du nom ou du alt de l'image)
        product["brand"] = None
        if product.get("img_alt"):
            # Format: "Nom produit Marque 100g"
            # On peut essayer d'extraire la marque depuis l'alt
            alt_parts = product["img_alt"].split()
            # La marque est souvent en avant-dernier ou dernier mot avant le poids
            for i, part in enumerate(alt_parts):
                if re.match(r'\d+g$|\d+c[L]?$', part):
                    if i > 0:
                        product["brand"] = alt_parts[i - 1]
                    break

        products.append(product)

    return pd.DataFrame(products)


