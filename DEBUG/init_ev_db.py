import sqlite3
import os
import sys

# ==============================================================================
# INSTRUCTIONS POUR EXECUTER LE SCRIPT DANS LA CONSOLE :
# 
# 1. Ouvrez votre terminal (PowerShell, CMD, ou terminal VS Code).
# 2. Assurez-vous d'être dans le répertoire racine du projet (t:\SCRAP\ScrapEV)
#    ou dans le répertoire 'DEBUG'.
# 3. Exécutez la commande suivante (si vous êtes dans le répertoire racine) :
#    python DEBUG/init_ev_db.py
# ==============================================================================

def main():
    # Définition des chemins vers les bases de données
    # Le script est supposé être lancé depuis la racine ou depuis utils/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source_db_path = os.path.join(base_dir, 'EauVive_prix.db')
    target_db_path = os.path.join(base_dir, 'EV.db')

    # Vérification de l'existence de la base source
    if not os.path.exists(source_db_path):
        print(f"Erreur : La base de données source '{source_db_path}' est introuvable.")
        sys.exit(1)

    print(f"Connexion à la base source : {source_db_path}")
    conn_src = sqlite3.connect(source_db_path)
    cursor_src = conn_src.cursor()
    
    # 1. Récupérer le schéma (les requêtes CREATE TABLE) pour PRODUITS et CATEGORIES
    tables_to_copy = ['PRODUITS', 'CATEGORIES']
    schemas = {}
    
    for table in tables_to_copy:
        cursor_src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
        result = cursor_src.fetchone()
        if result and result[0]:
            schemas[table] = result[0]
            print(f"Schéma de la table '{table}' récupéré.")
        else:
            print(f"Attention : La table '{table}' n'existe pas dans la base source.")

    conn_src.close()

    if not schemas:
        print("Aucune table à copier. Fin du script.")
        sys.exit(1)

    # 2. Création de la nouvelle base de données et des tables
    print(f"\nCréation de la nouvelle base : {target_db_path}")
    conn_tgt = sqlite3.connect(target_db_path)
    cursor_tgt = conn_tgt.cursor()

    for table, schema in schemas.items():
        cursor_tgt.execute(f"DROP TABLE IF EXISTS {table}")
        cursor_tgt.execute(schema)
        print(f"Table '{table}' créée avec succès dans EV.db.")

    # 3. Peuplement des tables à partir de la base source
    # On attache la base source à notre connexion cible pour copier les données efficacement
    cursor_tgt.execute(f"ATTACH DATABASE '{source_db_path}' AS source_db")
    
    print("\nCopie des données en cours...")
    for table in schemas.keys():
        # Copie de toutes les lignes de la source vers la cible
        cursor_tgt.execute(f"INSERT INTO {table} SELECT * FROM source_db.{table}")
        
        # Récupération du nombre de lignes insérées
        cursor_tgt.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor_tgt.fetchone()[0]
        print(f"-> {count} lignes insérées dans la table '{table}'.")
        
    conn_tgt.commit()
    conn_tgt.close()
    
    print("\nOpération terminée avec succès ! La base de données EV.db est prête.")

if __name__ == '__main__':
    main()
