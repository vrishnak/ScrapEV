import sqlite3
from typing import List, Optional
import os


def get_db_connection(db_path: str = "EauVive_prix.db") -> sqlite3.Connection:
    """
    Crée une connexion à la base de données SQLite.

    Args:
        db_path: Chemin vers le fichier de base de données

    Returns:
        Connexion SQLite

    Raises:
        FileNotFoundError: Si le fichier de base de données n'existe pas
        sqlite3.Error: En cas d'erreur de connexion
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Base de données introuvable : {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par nom
        return conn
    except sqlite3.Error as e:
        raise sqlite3.Error(f"Erreur de connexion à la base : {e}")


def get_marques_uniques(
        db_path: str = "EauVive_prix.db",
        exclude_null: bool = True,
        exclude_empty: bool = True
) -> List[str]:
    """
    Récupère la liste des marques uniques de la table PRODUITS.

    Args:
        db_path: Chemin vers le fichier de base de données SQLite
        exclude_null: Exclure les valeurs NULL
        exclude_empty: Exclure les chaînes vides ou composées uniquement d'espaces

    Returns:
        Liste triée alphabétiquement des marques uniques

    Example:
        >>> marques = get_marques_uniques("EauVive_prix.db")
        >>> print(marques)
        ['Cristaline', 'Evian', 'Volvic', ...]
    """
    conn = None
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        # Construction de la requête
        query = "SELECT DISTINCT marque FROM PRODUITS"
        conditions = []

        if exclude_null:
            conditions.append("marque IS NOT NULL")

        if exclude_empty:
            conditions.append("TRIM(marque) != ''")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY marque COLLATE NOCASE ASC"

        cursor.execute(query)
        results = cursor.fetchall()

        # Extraction des valeurs
        marques = [row[0] for row in results]

        return marques

    except sqlite3.Error as e:
        print(f"Erreur SQL : {e}")
        return []
    except FileNotFoundError as e:
        print(f"Erreur : {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_marques_with_count(
        db_path: str = "EauVive_prix.db"
) -> List[tuple]:
    """
    Récupère les marques uniques avec le nombre de produits associés.

    Args:
        db_path: Chemin vers le fichier de base de données SQLite

    Returns:
        Liste de tuples (marque, nombre_de_produits) triée par marque
    """
    conn = None
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        query = """
            SELECT marque, COUNT(*) as nb_produits
            FROM PRODUITS
            WHERE marque IS NOT NULL AND TRIM(marque) != ''
            GROUP BY marque
            ORDER BY marque COLLATE NOCASE ASC
        """

        cursor.execute(query)
        return cursor.fetchall()

    except sqlite3.Error as e:
        print(f"Erreur SQL : {e}")
        return []
    finally:
        if conn:
            conn.close()


# Test rapide si exécuté directement
if __name__ == "__main__":
    marques = get_marques_uniques("EauVive_prix.db")
    print(f"Nombre de marques uniques : {len(marques)}")
    for marque in marques:
        print(f"  - {marque}")