"""
Création du schéma de la base de données Eau Vive.
À exécuter UNE SEULE FOIS (ou en cas de recréation de la base).

Usage :
    python -m utils.schema_db [chemin_db]

Par défaut : EauVive_prix.db
"""
import sqlite3
import sys
import os

SCHEMA_SQL = """
-- Table des catégories (avec hiérarchie)
CREATE TABLE IF NOT EXISTS CATEGORIES (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    parent_id INTEGER,
    FOREIGN KEY (parent_id) REFERENCES CATEGORIES(id),
    UNIQUE(nom, parent_id)
);

-- Table des produits - code_interne est la clé UNIQUE
CREATE TABLE IF NOT EXISTS PRODUITS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_interne TEXT UNIQUE NOT NULL,
    ean TEXT,
    description TEXT NOT NULL,
    marque TEXT,
    volume TEXT,
    lien_fiche TEXT,
    caracteristique TEXT,
    url_img TEXT,
    categorie_id INTEGER,
    ean_valide INTEGER DEFAULT 0,
    date_validation DATE,
    FOREIGN KEY (categorie_id) REFERENCES CATEGORIES(id)
);

-- Table pour les conflits EAN
CREATE TABLE IF NOT EXISTS CONFLITS_EAN (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_interne_1 TEXT NOT NULL,
    code_interne_2 TEXT NOT NULL,
    ean TEXT NOT NULL,
    date_detection DATE NOT NULL,
    statut TEXT DEFAULT 'en_attente',
    commentaire TEXT,
    FOREIGN KEY (code_interne_1) REFERENCES PRODUITS(code_interne),
    FOREIGN KEY (code_interne_2) REFERENCES PRODUITS(code_interne)
);

-- Table des magasins
CREATE TABLE IF NOT EXISTS MAGASINS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT UNIQUE NOT NULL,
    nomcsv TEXT,
    adresse TEXT,
    code_postal TEXT,
    ville TEXT,
    livraison_domicile INTEGER,
    retrait_magasin INTEGER,
    lien TEXT,
    sdv INTEGER
);

-- Table des relevés de prix (prix stockés en TEXTE)
CREATE TABLE IF NOT EXISTS RELEVES_PRIX (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produit_id INTEGER NOT NULL,
    magasin_id INTEGER NOT NULL,
    date_releve DATE NOT NULL,
    prix TEXT NOT NULL,
    prix_old TEXT,
    prix_unit TEXT,
    FOREIGN KEY (produit_id) REFERENCES PRODUITS(id),
    FOREIGN KEY (magasin_id) REFERENCES MAGASINS(id),
    UNIQUE(produit_id, magasin_id, date_releve)
);

-- Index utiles pour les requêtes fréquentes
CREATE INDEX IF NOT EXISTS idx_releves_magasin_date
    ON RELEVES_PRIX(magasin_id, date_releve);
CREATE INDEX IF NOT EXISTS idx_releves_produit
    ON RELEVES_PRIX(produit_id);
CREATE INDEX IF NOT EXISTS idx_produits_code
    ON PRODUITS(code_interne);
CREATE INDEX IF NOT EXISTS idx_produits_categorie
    ON PRODUITS(categorie_id);
"""


def creer_base(db_path="EauVive_prix.db", verbose=True):
    """Crée la base et toutes les tables si elles n'existent pas.

    Returns:
        bool: True si succès
    """
    if verbose:
        print(f"🗄️  Création / vérification du schéma dans : {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()

        # Vérification
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        if verbose:
            print(f"✅ Tables présentes : {', '.join(tables)}")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de la création du schéma : {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "EauVive_prix.db"
    if os.path.exists(db_path):
        reponse = input(
            f"⚠️  Le fichier {db_path} existe déjà. "
            f"Les tables manquantes seront créées, sans toucher aux existantes. "
            f"Continuer ? (o/N) "
        )
        if reponse.lower() != "o":
            print("Annulé.")
            sys.exit(0)
    creer_base(db_path)