# utils/recherche_EV.py
"""
Module de recherche pour le Dashboard EAU VIVE
Contient toutes les fonctions liées à la recherche de produits
"""

import pandas as pd
import sqlite3
from typing import Optional, Tuple, List, Dict, Any, Union

# ============================================
# MODE DEBUG_EAN
# - True  : Affiche uniquement les produits sans EAN
# - False : Comportement normal (tous les produits)
# ============================================
DEBUG_EAN = True  # Mettre à False pour désactiver le mode debug

# Mots vides (stop words) en français
STOP_WORDS = {
    'de', 'à', 'le', 'la', 'les', 'des', 'et', 'ou', 'du', 'au',
    'aux', 'en', 'sur', 'sous', 'dans', 'pour', 'par', 'avec',
    'sans', 'entre', 'vers', 'chez', 'contre', 'depuis', 'pendant'
}


def appliquer_filtre_debug_ean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applique le filtre DEBUG_EAN sur un DataFrame

    Args:
        df: DataFrame à filtrer

    Returns:
        DataFrame filtré selon le mode DEBUG_EAN
    """
    if not DEBUG_EAN or df.empty:
        return df

    # Filtrer les produits sans EAN
    mask_no_ean = (
            df['ean'].isna() |
            (df['ean'].astype(str).str.strip() == "") |
            (df['ean'].astype(str).str.strip() == "None")
    )

    return df[mask_no_ean].copy()


def rechercher_par_mots_cles_stricte(
        conn: sqlite3.Connection,
        search_query: str
) -> pd.DataFrame:
    """
    Recherche stricte par mots-clés (méthode actuelle)
    Cherche la sous-chaîne exacte dans la description

    Args:
        conn: Connexion à la base de données
        search_query: Chaîne de recherche (partielle)

    Returns:
        DataFrame avec les produits trouvés
    """
    if not search_query:
        return pd.DataFrame()

    query = f"%{search_query}%"
    df_search = pd.read_sql_query(
        """SELECT id, code_interne, ean, description, marque 
           FROM PRODUITS WHERE description LIKE ?""",
        conn,
        params=(query,)
    )

    # Application du filtre DEBUG_EAN
    return appliquer_filtre_debug_ean(df_search)


def rechercher_par_mots_cles_souple(
        conn: sqlite3.Connection,
        search_query: str,
        ignorer_stop_words: bool = True,
        score_min: float = 0.3
) -> pd.DataFrame:
    """
    Recherche souple par mots-clés (ordre indépendant, score de pertinence)

    Args:
        conn: Connexion à la base de données
        search_query: Chaîne de recherche
        ignorer_stop_words: Si True, ignore les mots vides
        score_min: Score minimum pour qu'un produit soit retenu (0-1)

    Returns:
        DataFrame avec les produits trouvés et leur score
    """
    if not search_query:
        return pd.DataFrame()

    # Nettoyer et découper la recherche
    search_clean = search_query.lower().strip()

    # Extraire les mots significatifs
    mots = search_clean.split()

    if ignorer_stop_words:
        mots = [mot for mot in mots if mot not in STOP_WORDS and len(mot) > 2]

    if not mots:
        return pd.DataFrame()

    # Construction de la requête SQL avec score de pertinence
    conditions = []
    params = []

    # Pour chaque mot, une condition LIKE dans le WHERE
    for mot in mots:
        conditions.append("LOWER(description) LIKE ?")
        params.append(f"%{mot}%")

    # Construction du score (nombre de mots trouvés)
    score_cases = []
    for mot in mots:
        score_cases.append("(CASE WHEN LOWER(description) LIKE ? THEN 1 ELSE 0 END)")
        params.append(f"%{mot}%")  # Ajout des paramètres supplémentaires pour le score

    # Calcul du score en pourcentage
    score_sql = f"({'+'.join(score_cases)}) * 1.0 / {len(mots)}"

    sql = f"""
        SELECT id, code_interne, ean, description, marque,
               {score_sql} as score
        FROM PRODUITS 
        WHERE {' AND '.join(conditions)}
        ORDER BY score DESC, description
    """

    # Exécuter la requête
    df_result = pd.read_sql_query(sql, conn, params=params)

    # Filtrer par score minimum
    if score_min > 0:
        df_result = df_result[df_result['score'] >= score_min]

    # Application du filtre DEBUG_EAN
    return appliquer_filtre_debug_ean(df_result)


def rechercher_par_mots_cles_hybride(
        conn: sqlite3.Connection,
        search_query: str,
        mode: str = "souple"
) -> pd.DataFrame:
    """
    Point d'entrée unique pour la recherche par mots-clés

    Args:
        conn: Connexion à la base de données
        search_query: Chaîne de recherche
        mode: "stricte" ou "souple"

    Returns:
        DataFrame avec les produits trouvés
    """
    if mode == "stricte":
        return rechercher_par_mots_cles_stricte(conn, search_query)
    else:  # mode souple
        return rechercher_par_mots_cles_souple(conn, search_query)


def rechercher_par_ean(
        conn: sqlite3.Connection,
        ean: str
) -> pd.DataFrame:
    """
    Recherche un produit par son code EAN exact

    Args:
        conn: Connexion à la base de données
        ean: Code EAN à rechercher

    Returns:
        DataFrame avec le produit trouvé (ou vide)
    """
    if not ean:
        return pd.DataFrame()

    df_search = pd.read_sql_query(
        """SELECT id, code_interne, ean, description, marque 
           FROM PRODUITS WHERE ean = ?""",
        conn,
        params=(ean,)
    )

    # NOTE: En mode DEBUG_EAN, la recherche par EAN exact ne devrait pas être filtrée
    # car on cherche justement un EAN spécifique
    if DEBUG_EAN:
        # On garde le résultat même s'il a un EAN (car on cherche un EAN spécifique)
        return df_search
    else:
        return df_search


def rechercher_par_code_interne(
        conn: sqlite3.Connection,
        code_interne: str
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Recherche un produit par son code interne exact

    Args:
        conn: Connexion à la base de données
        code_interne: Code interne à rechercher

    Returns:
        Tuple (trouvé, id_produit, description)
    """
    if not code_interne:
        return False, None, None

    df_search = pd.read_sql_query(
        """SELECT id, code_interne, ean, description 
           FROM PRODUITS WHERE code_interne = ?""",
        conn,
        params=(code_interne,)
    )

    if not df_search.empty:
        # En mode DEBUG_EAN, on filtre aussi
        if DEBUG_EAN:
            # Vérifier si le produit trouvé a un EAN
            ean = df_search['ean'].values[0]
            if pd.isna(ean) or str(ean).strip() in ['', 'None']:
                return True, df_search['id'].values[0], df_search['description'].values[0]
            else:
                # Le produit a un EAN, on ne le retourne pas en mode DEBUG
                return False, None, None
        else:
            return True, df_search['id'].values[0], df_search['description'].values[0]

    return False, None, None


def formater_affichage_produit(
        df: pd.DataFrame,
        avec_ean: bool = True,
        avec_score: bool = False
) -> List[str]:
    """
    Formate les produits pour l'affichage dans un selectbox

    Args:
        df: DataFrame des produits
        avec_ean: Si True, ajoute un indicateur pour les produits sans EAN
        avec_score: Si True, ajoute le score de pertinence

    Returns:
        Liste des chaînes formatées
    """
    if df.empty:
        return []

    # Créer une copie pour éviter de modifier l'original
    df_copy = df.copy()

    # Format de base
    df_copy['display'] = df_copy['code_interne'].astype(str) + " - " + df_copy['description'] + " (" + df_copy[
        'marque'].fillna('Sans marque') + ")"

    # Ajout du score si demandé
    if avec_score and 'score' in df_copy.columns:
        # Utiliser apply pour formater chaque ligne individuellement
        df_copy['display'] = df_copy.apply(
            lambda row: row['display'] + f" [Score: {row['score']:.0%}]",
            axis=1
        )

    # Indicateur pour les produits sans EAN
    if avec_ean:
        mask_no_ean = (
                df_copy['ean'].isna() |
                (df_copy['ean'].astype(str).str.strip() == "") |
                (df_copy['ean'].astype(str).str.strip() == "None")
        )
        df_copy.loc[mask_no_ean, 'display'] = "⚠️ [SANS EAN] " + df_copy.loc[mask_no_ean, 'display']

    # Si on est en mode DEBUG_EAN, ajouter un indicateur supplémentaire
    if DEBUG_EAN:
        df_copy['display'] = "🔍 [DEBUG EAN] " + df_copy['display']

    return df_copy['display'].tolist()


def obtenir_id_depuis_affichage(
        df: pd.DataFrame,
        display_value: str
) -> Optional[int]:
    """
    Récupère l'ID du produit à partir de sa valeur d'affichage

    Args:
        df: DataFrame des produits
        display_value: Valeur affichée sélectionnée

    Returns:
        ID du produit ou None si non trouvé
    """
    if df.empty or not display_value:
        return None

    # Nettoyer la valeur d'affichage pour la comparaison
    clean_value = display_value

    # Enlever le préfixe DEBUG_EAN si présent
    if clean_value.startswith("🔍 [DEBUG EAN] "):
        clean_value = clean_value[len("🔍 [DEBUG EAN] "):]

    # Enlever le préfixe "⚠️ [SANS EAN] " s'il existe
    if clean_value.startswith("⚠️ [SANS EAN] "):
        clean_value = clean_value[len("⚠️ [SANS EAN] "):]

    # Enlever le score s'il existe
    if " [Score:" in clean_value:
        clean_value = clean_value.split(" [Score:")[0]

    # Créer une colonne de comparaison nettoyée
    df_clean = df.copy()
    df_clean['display_clean'] = df_clean['code_interne'].astype(str) + " - " + df_clean['description'] + " (" + \
                                df_clean['marque'].fillna('Sans marque') + ")"

    result = df_clean.loc[df_clean['display_clean'] == clean_value, 'id']
    return result.values[0] if not result.empty else None


def gerer_recherche_nom(
        conn: sqlite3.Connection,
        search_query: str,
        mode: str = "souple"
) -> Tuple[pd.DataFrame, Optional[int], List[str]]:
    """
    Fonction complète pour la recherche par nom

    Args:
        conn: Connexion à la base de données
        search_query: Chaîne de recherche
        mode: "stricte" ou "souple"

    Returns:
        Tuple (df_produits, id_selectionne, liste_affichage)
    """
    df_search = rechercher_par_mots_cles_hybride(conn, search_query, mode)

    if df_search.empty:
        return df_search, None, []

    # Détecter si le score est présent
    avec_score = 'score' in df_search.columns
    display_list = formater_affichage_produit(df_search, avec_ean=True, avec_score=avec_score)
    return df_search, None, display_list


def gerer_recherche_ean(
        conn: sqlite3.Connection,
        ean: str
) -> Tuple[pd.DataFrame, Optional[int], List[str]]:
    """
    Fonction complète pour la recherche par EAN

    Args:
        conn: Connexion à la base de données
        ean: Code EAN

    Returns:
        Tuple (df_produits, id_selectionne, liste_affichage)
    """
    df_search = rechercher_par_ean(conn, ean)

    if df_search.empty:
        return df_search, None, []

    display_list = formater_affichage_produit(df_search, avec_ean=False)
    return df_search, None, display_list


def gerer_recherche_code_interne(
        conn: sqlite3.Connection,
        code_interne: str
) -> Tuple[bool, Optional[int], str]:
    """
    Fonction complète pour la recherche par code interne

    Args:
        conn: Connexion à la base de données
        code_interne: Code interne

    Returns:
        Tuple (trouve, id_produit, description)
    """
    return rechercher_par_code_interne(conn, code_interne)


def obtenir_info_produit(
        conn: sqlite3.Connection,
        produit_id: int
) -> pd.DataFrame:
    """
    Récupère toutes les informations d'un produit

    Args:
        conn: Connexion à la base de données
        produit_id: ID du produit

    Returns:
        DataFrame avec les informations du produit
    """
    return pd.read_sql_query(
        "SELECT * FROM PRODUITS WHERE id = ?",
        conn,
        params=(int(produit_id),)
    )


def obtenir_historique_prix(
        conn: sqlite3.Connection,
        produit_id: int
) -> pd.DataFrame:
    """
    Récupère l'historique des prix d'un produit

    Args:
        conn: Connexion à la base de données
        produit_id: ID du produit

    Returns:
        DataFrame avec l'historique des prix
    """
    query_prix = """
        SELECT r.date_releve, r.prix, r.prix_old, r.prix_unit, m.nom as magasin
        FROM RELEVES_PRIX r
        JOIN MAGASINS m ON r.magasin_id = m.id
        WHERE r.produit_id = ?
        ORDER BY r.date_releve ASC
    """
    return pd.read_sql_query(query_prix, conn, params=(int(produit_id),))


# Fonction utilitaire pour obtenir des statistiques sur la recherche
def get_recherche_stats(conn) -> Dict[str, Any]:
    """
    Récupère des statistiques sur la base de données pour la recherche

    Args:
        conn: Connexion à la base de données

    Returns:
        Dict avec les statistiques
    """
    stats = {}

    # Nombre total de produits
    stats['total_produits'] = pd.read_sql_query(
        "SELECT COUNT(*) as count FROM PRODUITS", conn
    )['count'].values[0]

    # Nombre de produits sans EAN
    stats['sans_ean'] = pd.read_sql_query(
        "SELECT COUNT(*) as count FROM PRODUITS WHERE ean IS NULL OR ean = '' OR ean = 'None'", conn
    )['count'].values[0]

    # Top 10 des marques
    stats['top_marques'] = pd.read_sql_query(
        """SELECT marque, COUNT(*) as count 
           FROM PRODUITS 
           WHERE marque IS NOT NULL AND marque != ''
           GROUP BY marque 
           ORDER BY count DESC 
           LIMIT 10""", conn
    )

    # Ajouter l'état du mode DEBUG_EAN dans les statistiques
    stats['debug_ean_actif'] = DEBUG_EAN

    return stats


# Fonction pour afficher l'état du mode DEBUG_EAN
def get_debug_ean_status() -> Dict[str, Any]:
    """
    Retourne l'état actuel du mode DEBUG_EAN

    Returns:
        Dict avec l'état du mode debug
    """
    return {
        'actif': DEBUG_EAN,
        'message': "🔍 Mode DEBUG_EAN ACTIF - Affichage uniquement des produits sans EAN" if DEBUG_EAN else "Mode DEBUG_EAN inactif - Affichage normal"
    }