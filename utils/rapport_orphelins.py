# utils/rapport_orphelins.py
"""
Fonction indépendante : détection des références produits
absentes de la base au moment de l'import.
"""

from datetime import datetime


def formater_fiche_produit(item):
    """Retourne une chaîne multi-lignes décrivant un produit JSON.

    Accepte un dict issu d'un fichier V5_*.json.
    Tous les champs sont optionnels.
    """
    ref_id      = str(item.get('ref_id', '?')).strip() or '?'
    description = (item.get('description') or '(sans description)').strip()
    ean         = (item.get('ean') or '').strip() or 'N/A'
    marque      = (item.get('marque') or '').strip() or 'N/A'
    volume      = (item.get('volume') or '').strip() or 'N/A'
    prix        = (item.get('prix') or '').strip() or 'N/A'
    anc_prix    = (item.get('ancien_prix') or '').strip()
    prix_unit   = (item.get('volume_price') or '').strip() or 'N/A'
    lien        = (item.get('lien') or '').strip() or 'N/A'
    tags        = item.get('tags') or []

    # Tags -> texte
    if isinstance(tags, list):
        tags_txt = '; '.join(
            str(t.get('text', '')) if isinstance(t, dict) else str(t)
            for t in tags
        ) or 'N/A'
    else:
        tags_txt = str(tags) or 'N/A'

    lignes = [
        f"    ┌─ Réf. interne : {ref_id}",
        f"    │  Description  : {description}",
        f"    │  Marque       : {marque}",
        f"    │  EAN          : {ean}",
        f"    │  Volume       : {volume}",
        f"    │  Prix         : {prix}",
    ]
    if anc_prix:
        lignes.append(f"    │  Ancien prix  : {anc_prix}")
    lignes += [
        f"    │  Prix unitaire: {prix_unit}",
        f"    │  Tags         : {tags_txt}",
        f"    └─ Lien         : {lien}",
    ]
    return '\n'.join(lignes)


def detecter_references_absentes(items, db, callback=None):
    """
    Parcourt une liste d'items JSON et identifie ceux dont le ref_id
    n'existe PAS encore dans la table PRODUITS.

    Paramètres
    ----------
    items : list[dict]
        Liste des produits du fichier JSON.
    db : GestionnaireDB
        Instance du gestionnaire de base de données (doit exposer
        `_get_connection()` et posséder une table PRODUITS).
    callback : callable(message, type_message), optionnel
        Si fourni, appelé pour chaque référence absente détectée avec
        le message formaté et le type 'warning'. Peut être utilisé
        pour alimenter le journal de la GUI.

    Retour
    ------
    list[dict]
        Liste des items (dict complets) dont le ref_id était absent.
    """
    conn, cursor = db._get_connection()
    absents = []

    for item in items:
        if not isinstance(item, dict):
            continue

        ref_id = str(item.get('ref_id', '')).strip()
        if not ref_id:
            continue

        cursor.execute(
            "SELECT 1 FROM PRODUITS WHERE code_interne = ? LIMIT 1",
            (ref_id,)
        )
        if cursor.fetchone() is None:
            absents.append(item)

            if callback:
                titre = (f"Référence {ref_id} absente de la base "
                         f"(nouveau produit détecté)")
                callback(f"{titre}\n{formater_fiche_produit(item)}", 'warning')

    return absents


def generer_rapport_orphelins(items_absents, chemin_sortie=None):
    """
    Génère un rapport texte à partir d'une liste d'items absents.

    Paramètres
    ----------
    items_absents : list[dict]
    chemin_sortie : str, optionnel
        Si fourni, écrit le rapport dans ce fichier (UTF-8).

    Retour
    ------
    str : le rapport au format texte.
    """
    if not items_absents:
        return "Aucune référence absente détectée."

    horodatage = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lignes = [
        "=" * 70,
        f"RAPPORT DES RÉFÉRENCES ABSENTES - {horodatage}",
        f"Nombre total : {len(items_absents)}",
        "=" * 70,
        "",
    ]
    for i, item in enumerate(items_absents, start=1):
        lignes.append(f"[{i}] {formater_fiche_produit(item)}")
        lignes.append("")

    rapport = '\n'.join(lignes)

    if chemin_sortie:
        with open(chemin_sortie, 'w', encoding='utf-8') as f:
            f.write(rapport)

    return rapport