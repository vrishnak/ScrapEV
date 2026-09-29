"""
Extraction des produits par magasin, avec les derniers relevés de prix.

Exporte un JSON au format :
{
  "magasin": "Eau Vive",
  "magasin_id": 1,
  "date_export": "2025-01-15T10:30:00",
  "produits": [
    {
      "code_interne": "...",
      "ean": "...",
      "description": "...",
      "marque": "...",
      "volume": "...",
      "lien_fiche": "...",
      "caracteristique": "...",
      "url_img": "...",
      "categorie_id": 3,
      "categorie_nom": "...",
      "date_releve": "2025-01-15",
      "prix": "3.50",
      "prix_old": "4.00",
      "prix_unit": "1.75 €/L"
    },
    ...
  ]
}
"""
import json
import os
from datetime import datetime


def extraire_produits_par_magasin(db, magasin_id, date_max=None):
    """Retourne tous les produits ayant un relevé pour ce magasin,
    avec le dernier relevé connu (éventuellement <= date_max).

    Args:
        db: instance de GestionnaireDB
        magasin_id (int): ID du magasin
        date_max (str, optionnel): date ISO max (YYYY-MM-DD)

    Returns:
        list[dict]: liste de dicts (données produit + dernier relevé)
    """
    conn, cursor = db._get_connection()

    # Sous-requête : pour chaque produit, la date du dernier relevé
    # pour ce magasin (<= date_max si fournie)
    params = [magasin_id]
    clause_date = ""
    if date_max:
        clause_date = "AND rp.date_releve <= ?"
        params.append(date_max)

    sql = f"""
        SELECT
            p.id,
            p.code_interne,
            p.ean,
            p.description,
            p.marque,
            p.volume,
            p.lien_fiche,
            p.caracteristique,
            p.url_img,
            p.categorie_id,
            c.nom AS categorie_nom,
            rp.date_releve,
            rp.prix,
            rp.prix_old,
            rp.prix_unit
        FROM PRODUITS p
        JOIN RELEVES_PRIX rp ON rp.produit_id = p.id
        LEFT JOIN CATEGORIES c ON c.id = p.categorie_id
        WHERE rp.magasin_id = ?
          {clause_date}
          AND rp.date_releve = (
              SELECT MAX(rp2.date_releve)
              FROM RELEVES_PRIX rp2
              WHERE rp2.produit_id = p.id
                AND rp2.magasin_id = ?
                {('AND rp2.date_releve <= ?' if date_max else '')}
          )
        ORDER BY p.description COLLATE NOCASE
    """

    # On doit répéter magasin_id et éventuellement date_max dans la sous-requête
    if date_max:
        params_final = [magasin_id, date_max, magasin_id, date_max]
    else:
        params_final = [magasin_id, magasin_id]

    cursor.execute(sql, params_final)
    lignes = cursor.fetchall()

    resultats = []
    for row in lignes:
        (pid, code_interne, ean, description, marque, volume,
         lien_fiche, caracteristique, url_img, categorie_id,
         categorie_nom, date_releve, prix, prix_old, prix_unit) = row

        resultats.append({
            "code_interne": code_interne,
            "ean": ean or "",
            "description": description or "",
            "marque": marque or "",
            "volume": volume or "",
            "lien_fiche": lien_fiche or "",
            "caracteristique": caracteristique or "",
            "url_img": url_img or "",
            "categorie_id": categorie_id,
            "categorie_nom": categorie_nom or "",
            "date_releve": date_releve,
            "prix": prix or "",
            "prix_old": prix_old or "",
            "prix_unit": prix_unit or "",
        })

    return resultats


def exporter_produits_magasin_json(db, magasin_id, chemin_sortie,
                                   date_max=None, callback=None):
    """Exporte en JSON les produits d'un magasin avec leur dernier relevé.

    Args:
        db: instance de GestionnaireDB
        magasin_id (int): ID du magasin
        chemin_sortie (str): chemin du fichier JSON de sortie
        date_max (str, optionnel): date ISO max
        callback (callable, optionnel): pour logs

    Returns:
        bool: True si succès
    """
    try:
        conn, cursor = db._get_connection()

        # Récupère le nom du magasin
        cursor.execute(
            "SELECT id, nom, nomcsv FROM MAGASINS WHERE id = ?",
            (magasin_id,)
        )
        mag = cursor.fetchone()
        if not mag:
            if callback:
                callback(f"Magasin id={magasin_id} introuvable", 'error')
            return False
        mag_id, mag_nom, mag_nomcsv = mag

        produits = extraire_produits_par_magasin(db, magasin_id, date_max)

        payload = {
            "magasin": mag_nom,
            "magasin_id": mag_id,
            "date_export": datetime.now().isoformat(timespec='seconds'),
            "date_max": date_max,
            "nb_produits": len(produits),
            "produits": produits,
        }

        os.makedirs(os.path.dirname(os.path.abspath(chemin_sortie)) or ".",
                    exist_ok=True)
        with open(chemin_sortie, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        if callback:
            callback(
                f"Exporté {len(produits)} produits du magasin "
                f"'{mag_nom}' vers {chemin_sortie}",
                'success'
            )
        return True

    except Exception as e:
        if callback:
            callback(f"Erreur export : {e}", 'error')
        import traceback
        traceback.print_exc()
        return False


def exporter_tous_magasins_json(db, dossier_sortie,
                                date_max=None, callback=None):
    """Exporte un JSON par magasin dans un dossier.

    Returns:
        list[str]: chemins des fichiers créés
    """
    conn, cursor = db._get_connection()
    cursor.execute("SELECT id, nom, nomcsv FROM MAGASINS ORDER BY nom")
    magasins = cursor.fetchall()

    fichiers = []
    os.makedirs(dossier_sortie, exist_ok=True)

    for mag_id, mag_nom, mag_nomcsv in magasins:
        nom_fichier = _nettoyer_nom(mag_nom) + ".json"
        chemin = os.path.join(dossier_sortie, nom_fichier)
        if exporter_produits_magasin_json(db, mag_id, chemin,
                                          date_max=date_max,
                                          callback=callback):
            fichiers.append(chemin)

    return fichiers


def _nettoyer_nom(nom):
    """Nettoie un nom pour en faire un nom de fichier."""
    import re
    import unicodedata
    if not isinstance(nom, str):
        nom = str(nom)
    nom = unicodedata.normalize("NFD", nom)
    nom = "".join(c for c in nom if unicodedata.category(c) != "Mn")
    nom = nom.replace(" ", "_")
    nom = re.sub(r'[<>:"/\\|?*]', "_", nom)
    return nom