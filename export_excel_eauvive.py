import sqlite3
import pandas as pd
import os
import re

def export_db_table_to_excel(db_name="EauVive_prix.db", output_name="DATA_EV/EauVive_Produits_Releves.xlsx"):
    """
    Exporte le contenu de la table PRODUITS jointe avec RELEVES_PRIX et MAGASINS vers un fichier Excel.
    Crée un onglet global et un onglet par magasin (avec le nom du magasin et le dernier prix relevé).
    """
    # Créer le répertoire de destination s'il n'existe pas
    output_dir = os.path.dirname(output_name)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(db_name):
        print(f"Erreur : Le fichier de base de données '{db_name}' est introuvable.")
        return

    print(f"Connexion à la base de données : {db_name}")
    conn = sqlite3.connect(db_name)
    
    try:
        print("Lecture et jointure des tables PRODUITS, RELEVES_PRIX et MAGASINS...")
        
        # Jointure avec la table MAGASINS pour obtenir le nom
        query = """
        SELECT 
            p.id AS produit_id_db,
            p.code_interne,
            p.ean,
            p.description,
            p.marque,
            p.volume,
            p.lien_fiche,
            p.caracteristique,
            p.url_img,
            p.categorie_id,
            p.ean_valide,
            p.date_validation,
            r.id AS releve_id,
            r.magasin_id,
            m.nom AS magasin_nom,
            r.date_releve,
            r.prix,
            r.prix_old,
            r.prix_unit
        FROM PRODUITS p
        LEFT JOIN RELEVES_PRIX r ON p.id = r.produit_id
        LEFT JOIN MAGASINS m ON r.magasin_id = m.id
        """
        
        # Lire les données dans un DataFrame Pandas
        df = pd.read_sql_query(query, conn)
        print(f"Total de {len(df)} lignes lues depuis la base de données.")
        
        # Convertir date_releve en datetime pour permettre un tri chronologique correct
        df['date_releve_dt'] = pd.to_datetime(df['date_releve'])
        
        print(f"Création du fichier Excel '{output_name}' avec plusieurs onglets (cela peut prendre quelques instants)...")
        # Utiliser ExcelWriter pour créer plusieurs feuilles dans le même fichier
        with pd.ExcelWriter(output_name, engine='openpyxl') as writer:
            
            # 1. Premier onglet : toutes les données
            print(" - Création de l'onglet principal 'Toutes_les_donnees'...")
            df_export = df.drop(columns=['date_releve_dt'])
            df_export.to_excel(writer, sheet_name='Toutes_les_donnees', index=False)
            
            # 2. Onglets par magasin
            # Récupérer la liste de tous les magasins uniques
            magasins_ids = df['magasin_id'].dropna().unique()
            
            for mag_id in sorted(magasins_ids):
                # Filtrer pour le magasin actuel
                df_mag = df[df['magasin_id'] == mag_id]
                
                # Récupérer le nom du magasin
                mag_noms = df_mag['magasin_nom'].dropna().unique()
                if len(mag_noms) > 0:
                    mag_nom = str(mag_noms[0])
                else:
                    try:
                        mag_id_int = int(mag_id)
                        mag_nom = f"Magasin_{mag_id_int}"
                    except:
                        mag_nom = f"Magasin_{mag_id}"
                
                # Nettoyer le nom pour Excel (pas de caractères interdits, max 31 caractères)
                # Excel interdit les caractères : \ / * ? : [ ]
                safe_name = re.sub(r'[\\/*?:\[\]]', '_', mag_nom)
                # Tronquer à 31 caractères max (limite Excel)
                safe_name = safe_name[:31].strip()
                # Éviter les noms d'onglets vides ou dupliqués
                if not safe_name:
                    safe_name = f"Magasin_{int(mag_id)}"
                    
                print(f" - Création de l'onglet '{safe_name}' (derniers prix)...")
                
                # Trier par ID de produit, puis par date décroissante (plus récent en premier)
                df_mag = df_mag.sort_values(by=['produit_id_db', 'date_releve_dt'], ascending=[True, False])
                
                # Ne conserver que la première ligne pour chaque produit (le dernier relevé)
                df_mag_last_price = df_mag.drop_duplicates(subset=['produit_id_db'], keep='first')
                
                # Nettoyer et exporter
                df_mag_export = df_mag_last_price.drop(columns=['date_releve_dt'])
                df_mag_export.to_excel(writer, sheet_name=safe_name, index=False)
                
        print("Exportation terminée avec succès !")
        
    except pd.io.sql.DatabaseError as e:
        print(f"Erreur de base de données : {e}")
    except ModuleNotFoundError:
        print("Erreur : Le module 'openpyxl' est requis pour exporter vers Excel. Veuillez l'installer avec : pip install openpyxl")
    except Exception as e:
        print(f"Une erreur inattendue est survenue : {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export_db_table_to_excel()
