# utils/recherche_EV.py
"""
Module de recherche pour le Dashboard EAU VIVE
Contient toutes les fonctions liées à la recherche de produits.
"""

import pandas as pd
import sqlite3
from typing import Optional, Tuple, List, Dict, Any, Union

# ============================================================
# CONFIGURATION GLOBALE
# ============================================================
# MODE DEBUG_EAN
#   True  : N'affiche que les produits SANS EAN (utile pour saisir les EAN manquants)
#   False : Comportement normal (tous les produits)
# ============================================================
DEBUG_EAN = True  # Mettre à False pour désactiver le mode debug

# Mots vides (stop words) en français
STOP_WORDS = {
    'de', 'à', 'le', 'la', 'les', 'des', 'et', 'ou', 'du', 'au',
    'aux', 'en', 'sur', 'sous', 'dans', 'pour', 'par', 'avec',
    'sans', 'entre', 'vers', 'chez', 'contre', 'depuis', 'pendant'
}


# ============================================================
# FONCTIONS DEBUG_EAN
# ============================================================
def enregistrer_ean(
        conn: sqlite3.Connection,
        produit_id,
        nouvel_ean
) -> Tuple[bool, str]:
    """
    Enregistre ou met à jour l'EAN d'un produit.

    Adaptation au schéma :
      - id  INTEGER PRIMARY KEY AUTOINCREMENT  -> cast int()
      - ean TEXT                                -> cast str | None

    Args:
        conn: Connexion SQLite
        produit_id: ID du produit (int, str numérique ou numpy.int64)
        nouvel_ean: Nouvel EAN (str, int) ou None pour effacer

    Returns:
        Tuple (succes: bool, message: str)
    """
    if not DEBUG_EAN:
        return False, "🔒 Modification EAN désactivée (DEBUG_EAN = False)."

    # --- NORMALISATION produit_id EN INT ---
    if produit_id is None:
        return False, "❌ Aucun produit sélectionné."
    try:
        produit_id_int = int(produit_id)
    except (TypeError, ValueError):
        return False, f"❌ ID produit invalide : {produit_id!r}"

    # --- NORMALISATION ean EN STR | None ---
    if nouvel_ean is None:
        ean_str = None
    else:
        ean_str = str(nouvel_ean).strip()
        if ean_str == "" or ean_str.lower() == "none":
            ean_str = None

    try:
        cur = conn.cursor()

        # 1) Vérifier existence du produit
        cur.execute("SELECT id, ean FROM PRODUITS WHERE id = ?", (produit_id_int,))
        row = cur.fetchone()
        if row is None:
            # Info debug utile : plage d'ids existants
            cur.execute("SELECT MIN(id), MAX(id), COUNT(*) FROM PRODUITS")
            mini, maxi, total = cur.fetchone()
            return False, (
                f"❌ Produit id={produit_id_int} introuvable. "
                f"(Plage ids : {mini}–{maxi}, total={total})"
            )

        ancien_ean = row[1]
        ancien_ean_str = str(ancien_ean).strip() if ancien_ean is not None else None

        # 2) Vérifier unicité de l'EAN si non vide
        if ean_str is not None:
            cur.execute(
                "SELECT id FROM PRODUITS WHERE ean = ? AND id != ?",
                (ean_str, produit_id_int)
            )
            doublon = cur.fetchone()
            if doublon:
                return False, f"⚠️ EAN {ean_str} déjà utilisé par le produit id={doublon[0]}."

        # 3) Écriture
        cur.execute(
            "UPDATE PRODUITS SET ean = ? WHERE id = ?",
            (ean_str, produit_id_int)
        )
        conn.commit()

        if ancien_ean_str == ean_str:
            return True, f"ℹ️ EAN inchangé : {ean_str or '(vide)'}"

        return True, f"✅ EAN enregistré pour id={produit_id_int} : {ean_str or '(vide)'}"

    except Exception as e:
        conn.rollback()
        return False, f"❌ Erreur SQL : {e}"

def appliquer_filtre_debug_ean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applique le filtre DEBUG_EAN sur un DataFrame.
    En mode DEBUG_EAN=True, ne conserve que les produits SANS EAN.

    Args:
        df: DataFrame à filtrer (doit contenir une colonne 'ean')

    Returns:
        DataFrame filtré
    """
    if not DEBUG_EAN or df.empty:
        return df

    mask_no_ean = (
            df['ean'].isna() |
            (df['ean'].astype(str).str.strip() == "") |
            (df['ean'].astype(str).str.strip().str.lower() == "none")
    )
    return df[mask_no_ean].copy()


def get_debug_ean_status() -> Dict[str, Any]:
    """
    Retourne l'état actuel du mode DEBUG_EAN.

    Returns:
        Dict avec 'actif' (bool) et 'message' (str)
    """
    return {
        'actif': DEBUG_EAN,
        'message': (
            "🔍 Mode DEBUG_EAN ACTIF - Affichage uniquement des produits sans EAN"
            if DEBUG_EAN
            else "Mode DEBUG_EAN inactif - Affichage normal"
        )
    }


# ============================================================
# RECHERCHE PAR MOTS-CLÉS
# ============================================================
def rechercher_par_mots_cles_stricte(
        conn: sqlite3.Connection,
        search_query: str
) -> pd.DataFrame:
    """
    Recherche stricte par mots-clés : la sous-chaîne exacte dans la description.

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
           FROM PRODUITS
           WHERE description LIKE ?""",
        conn,
        params=(query,)
    )
    return appliquer_filtre_debug_ean(df_search)

def _parser_mots_recherche(search_query: str) -> Tuple[List[str], List[str]]:
    """
    Sépare la requête en deux listes : mots à INCLURE et mots à EXCLURE.

    Convention :
        - Un mot précédé de '-' est exclu : "lessive -vrac"
        - Les mots vides (stop words) sont retirés des inclusions
        - Un '-' isolé ou '- ' est ignoré

    Returns:
        Tuple (mots_inclure, mots_exclure)
    """
    if not search_query:
        return [], []

    # Découpage en respectant les guillemets simples/doubles (bonus)
    # Ici on reste simple : split sur espaces
    tokens = search_query.lower().strip().split()

    mots_inclure: List[str] = []
    mots_exclure: List[str] = []

    for token in tokens:
        if token.startswith("-") and len(token) > 1:
            mot = token[1:].strip()
            if mot:
                mots_exclure.append(mot)
        else:
            mot = token.strip()
            if mot:
                mots_inclure.append(mot)

    return mots_inclure, mots_exclure


def rechercher_par_mots_cles_souple(
        conn: sqlite3.Connection,
        search_query: str,
        ignorer_stop_words: bool = True,
        score_min: float = 0.3
) -> pd.DataFrame:
    """
    Recherche souple par mots-clés (ordre indépendant, score de pertinence).
    Supporte l'exclusion de mots avec le préfixe '-' :
        ex: "lessive -vrac" -> contient "lessive" ET ne contient PAS "vrac"

    Args:
        conn: Connexion à la base de données
        search_query: Chaîne de recherche
        ignorer_stop_words: Si True, ignore les mots vides dans les inclusions
        score_min: Score minimum pour qu'un produit soit retenu (0-1)

    Returns:
        DataFrame avec les produits trouvés et leur score
    """
    if not search_query:
        return pd.DataFrame()

    # --- PARSING : séparer inclusions et exclusions ---
    mots_inclure, mots_exclure = _parser_mots_recherche(search_query)

    # Retirer les stop words des inclusions seulement
    if ignorer_stop_words:
        mots_inclure = [m for m in mots_inclure if m not in STOP_WORDS and len(m) > 2]

    # Si aucun mot à inclure ET aucun mot à exclure -> rien
    if not mots_inclure and not mots_exclure:
        return pd.DataFrame()

    # --- CONSTRUCTION SQL ---
    # Conditions d'inclusion (doivent toutes être présentes)
    conditions_inclure = []
    params_inclure = []
    for mot in mots_inclure:
        conditions_inclure.append("LOWER(description) LIKE ?")
        params_inclure.append(f"%{mot}%")

    # Conditions d'exclusion (aucune ne doit être présente)
    conditions_exclure = []
    params_exclure = []
    for mot in mots_exclure:
        conditions_exclure.append("LOWER(description) NOT LIKE ?")
        params_exclure.append(f"%{mot}%")

    # Score de pertinence (basé uniquement sur les inclusions)
    score_sql = "1.0"
    params_score = []
    if mots_inclure:
        score_cases = []
        for mot in mots_inclure:
            score_cases.append("(CASE WHEN LOWER(description) LIKE ? THEN 1 ELSE 0 END)")
            params_score.append(f"%{mot}%")
        score_sql = f"({'+'.join(score_cases)}) * 1.0 / {len(mots_inclure)}"

    # Assemblage WHERE
    where_parts = []
    if conditions_inclure:
        where_parts.append("(" + " AND ".join(conditions_inclure) + ")")
    if conditions_exclure:
        where_parts.append("(" + " AND ".join(conditions_exclure) + ")")
    where_sql = " AND ".join(where_parts) if where_parts else "1=1"

    # Ordre des paramètres : d'abord le SELECT (score), puis le WHERE
    # ⚠️ L'ordre doit correspondre à l'apparition dans la requête SQL finale.
    sql = f"""
        SELECT id, code_interne, ean, description, marque,
               {score_sql} as score
        FROM PRODUITS
        WHERE {where_sql}
        ORDER BY score DESC, description
    """

    # Ordre : score (SELECT) puis inclusions puis exclusions (WHERE)
    all_params = params_score + params_inclure + params_exclure

    df_result = pd.read_sql_query(sql, conn, params=all_params)

    if score_min > 0 and not df_result.empty and mots_inclure:
        df_result = df_result[df_result['score'] >= score_min]

    return appliquer_filtre_debug_ean(df_result)


def rechercher_par_mots_cles_hybride(
        conn: sqlite3.Connection,
        search_query: str,
        mode: str = "souple"
) -> pd.DataFrame:
    """
    Point d'entrée unique pour la recherche par mots-clés.

    Args:
        conn: Connexion à la base de données
        search_query: Chaîne de recherche
        mode: "stricte" ou "souple"

    Returns:
        DataFrame avec les produits trouvés
    """
    if mode == "stricte":
        return rechercher_par_mots_cles_stricte(conn, search_query)
    return rechercher_par_mots_cles_souple(conn, search_query)


# ============================================================
# RECHERCHE PAR EAN / CODE INTERNE
# ============================================================
def rechercher_par_ean(
        conn: sqlite3.Connection,
        ean: str
) -> pd.DataFrame:
    """
    Recherche un produit par son code EAN exact.

    Note: en mode DEBUG_EAN, on ne filtre PAS ici, car on cherche
    justement un EAN spécifique (souvent pour vérifier un doublon).

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
           FROM PRODUITS
           WHERE ean = ?""",
        conn,
        params=(ean,)
    )
    return df_search


def rechercher_par_code_interne(
        conn: sqlite3.Connection,
        code_interne: str
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Recherche un produit par son code interne exact.

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
           FROM PRODUITS
           WHERE code_interne = ?""",
        conn,
        params=(code_interne,)
    )

    if df_search.empty:
        return False, None, None

    # En mode DEBUG_EAN, on ne retourne que les produits sans EAN
    if DEBUG_EAN:
        ean = df_search['ean'].values[0]
        if pd.isna(ean) or str(ean).strip().lower() in ('', 'none'):
            return True, df_search['id'].values[0], df_search['description'].values[0]
        return False, None, None

    return True, df_search['id'].values[0], df_search['description'].values[0]


# ============================================================
# FORMATAGE & AFFICHAGE
# ============================================================
def formater_affichage_produit(
        df: pd.DataFrame,
        avec_ean: bool = True,
        avec_score: bool = False
) -> List[str]:
    """
    Formate les produits pour l'affichage dans un selectbox.

    Args:
        df: DataFrame des produits
        avec_ean: Si True, ajoute un indicateur pour les produits sans EAN
        avec_score: Si True, ajoute le score de pertinence

    Returns:
        Liste des chaînes formatées
    """
    if df.empty:
        return []

    df_copy = df.copy()

    df_copy['display'] = (
            df_copy['code_interne'].astype(str)
            + " - "
            + df_copy['description']
            + " ("
            + df_copy['marque'].fillna('Sans marque')
            + ")"
    )

    if avec_score and 'score' in df_copy.columns:
        df_copy['display'] = df_copy.apply(
            lambda row: row['display'] + f" [Score: {row['score']:.0%}]",
            axis=1
        )

    if avec_ean:
        mask_no_ean = (
                df_copy['ean'].isna() |
                (df_copy['ean'].astype(str).str.strip() == "") |
                (df_copy['ean'].astype(str).str.strip().str.lower() == "none")
        )
        df_copy.loc[mask_no_ean, 'display'] = (
                "⚠️ [SANS EAN] " + df_copy.loc[mask_no_ean, 'display']
        )

    if DEBUG_EAN:
        df_copy['display'] = "🔍 [DEBUG EAN] " + df_copy['display']

    return df_copy['display'].tolist()


def obtenir_id_depuis_affichage(
        df: pd.DataFrame,
        display_value: str
) -> Optional[int]:
    """
    Récupère l'ID du produit à partir de sa valeur d'affichage.

    Args:
        df: DataFrame des produits
        display_value: Valeur affichée sélectionnée

    Returns:
        ID du produit ou None si non trouvé
    """
    if df.empty or not display_value:
        return None

    clean_value = display_value

    # Retirer les préfixes ajoutés à l'affichage
    for prefix in ("🔍 [DEBUG EAN] ", "⚠️ [SANS EAN] "):
        if clean_value.startswith(prefix):
            clean_value = clean_value[len(prefix):]

    # Retirer le score
    if " [Score:" in clean_value:
        clean_value = clean_value.split(" [Score:")[0]

    # Reconstruire la clé d'affichage pour comparaison
    df_clean = df.copy()
    df_clean['display_clean'] = (
            df_clean['code_interne'].astype(str)
            + " - "
            + df_clean['description']
            + " ("
            + df_clean['marque'].fillna('Sans marque')
            + ")"
    )

    result = df_clean.loc[df_clean['display_clean'] == clean_value, 'id']
    return result.values[0] if not result.empty else None


# ============================================================
# POINTS D'ENTRÉE HAUT NIVEAU (utilisés par le dashboard)
# ============================================================
def gerer_recherche_nom(
        conn: sqlite3.Connection,
        search_query: str,
        mode: str = "souple"
) -> Tuple[pd.DataFrame, Optional[int], List[str]]:
    """
    Fonction complète pour la recherche par nom.

    Returns:
        Tuple (df_produits, id_selectionne, liste_affichage)
    """
    df_search = rechercher_par_mots_cles_hybride(conn, search_query, mode)

    if df_search.empty:
        return df_search, None, []

    avec_score = 'score' in df_search.columns
    display_list = formater_affichage_produit(df_search, avec_ean=True, avec_score=avec_score)
    return df_search, None, display_list


def gerer_recherche_ean(
        conn: sqlite3.Connection,
        ean: str
) -> Tuple[pd.DataFrame, Optional[int], List[str]]:
    """
    Fonction complète pour la recherche par EAN.

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
    Fonction complète pour la recherche par code interne.

    Returns:
        Tuple (trouve, id_produit, description)
    """
    return rechercher_par_code_interne(conn, code_interne)


# ============================================================
# RÉCUPÉRATION DES DONNÉES PRODUIT
# ============================================================
def obtenir_info_produit(
        conn: sqlite3.Connection,
        produit_id: int
) -> pd.DataFrame:
    """
    Récupère toutes les informations d'un produit.
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
    Récupère l'historique des prix d'un produit.
    """
    query_prix = """
        SELECT r.date_releve, r.prix, r.prix_old, r.prix_unit, m.nom as magasin
        FROM RELEVES_PRIX r
        JOIN MAGASINS m ON r.magasin_id = m.id
        WHERE r.produit_id = ?
        ORDER BY r.date_releve ASC
    """
    return pd.read_sql_query(query_prix, conn, params=(int(produit_id),))


# ============================================================
# STATISTIQUES
# ============================================================
def get_recherche_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Récupère des statistiques sur la base de données pour la recherche.

    Returns:
        Dict avec les statistiques
    """
    stats: Dict[str, Any] = {}

    stats['total_produits'] = pd.read_sql_query(
        "SELECT COUNT(*) as count FROM PRODUITS", conn
    )['count'].values[0]

    stats['sans_ean'] = pd.read_sql_query(
        """SELECT COUNT(*) as count FROM PRODUITS
           WHERE ean IS NULL OR ean = '' OR LOWER(ean) = 'none'""",
        conn
    )['count'].values[0]

    stats['top_marques'] = pd.read_sql_query(
        """SELECT marque, COUNT(*) as count
           FROM PRODUITS
           WHERE marque IS NOT NULL AND marque != ''
           GROUP BY marque
           ORDER BY count DESC
           LIMIT 10""",
        conn
    )

    stats['debug_ean_actif'] = DEBUG_EAN

    return stats