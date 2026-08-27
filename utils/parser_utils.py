from bs4 import BeautifulSoup

def get_last_page_number(html_content):
    """
    Extrait le numéro de la dernière page depuis le code HTML de la pagination.
    Cherche l'avant-dernière balise <li> dans <ul class="pagination products">.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    pagination = soup.find('ul', class_='pagination products')
    
    if not pagination:
        return 1
        
    li_elements = pagination.find_all('li')
    
    if len(li_elements) >= 2:
        # L'avant-dernière balise <li>
        last_page_li = li_elements[-2]
        link = last_page_li.find('a')
        if link and link.text.strip().isdigit():
            return int(link.text.strip())
            
    return 1

def parse_products_from_html(html_content):
    """
    Parse les produits depuis le code HTML et extrait les informations demandées.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    products = []
    
    cards = soup.find_all('div', class_='product-card')
    
    for card in cards:
        product_data = {
            'ref_id': '',
            'description': '',
            'ean': '',
            'prix': '',
            'ancien_prix': '',
            'volume_price': '',
            'lien': ''
        }
        
        # Titre et lien
        title_div = card.find('div', class_='product-title')
        if title_div:
            link_tag = title_div.find('a')
            if link_tag:
                lien = link_tag.get('href', '')
                product_data['description'] = link_tag.text.strip()
                product_data['lien'] = lien
                
                if '_' in lien:
                    last_part = lien.split('_')[-1]
                    digits = ''.join(filter(str.isdigit, last_part))
                    product_data['ref_id'] = digits
                
        # Prix, ancien prix et volumes
        prices_container = card.find('div', class_='product-prices')
        if prices_container:
            # Recherche du prix et du prix barré dans 'product-price-row'
            price_span = prices_container.find('span', class_='product-price')
            if price_span:
                product_data['prix'] = price_span.text.strip()
                
            not_price_span = prices_container.find('span', class_='product-not-price')
            if not_price_span:
                product_data['ancien_prix'] = not_price_span.text.strip()
                
            # Extraction du volume_price
            type_spans = prices_container.find_all('span', class_='product-price-type')
            
            for span in type_spans:
                text = span.text.strip()
                if "/" in text:
                    product_data['volume_price'] = text
                else:
                    # On garde aussi volume si jamais il est utile
                    product_data['volume'] = text
                
        products.append(product_data)
        
    return products
