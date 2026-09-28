import sqlite3
import os

def corriger_base():
    # Déterminer le chemin absolu vers la base de données
    # Puisque ce script est dans le dossier DEBUG, la BDD est dans le dossier parent
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "..", "EauVive_prix.db")
    db_path = os.path.abspath(db_path)
    
    print(f"Connexion à la base de données : {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Dictionnaire des fusions: id_doublon -> id_a_conserver
    fusions = {
        38: 5,   # Belfort_-_Andelnans -> Belfort - Andelnans
        39: 12   # Brie-et-Angonnes -> Brié-et-Angonnes
    }
    
    for id_doublon, id_conserve in fusions.items():
        print(f"\nFusion de l'ID {id_doublon} vers l'ID {id_conserve}...")
        
        # 1. Mettre à jour les relevés de prix
        # On utilise UPDATE OR IGNORE pour éviter les conflits d'unicité 
        # (si le même produit a été relevé le même jour pour les deux IDs)
        cursor.execute('''
            UPDATE OR IGNORE RELEVES_PRIX 
            SET magasin_id = ? 
            WHERE magasin_id = ?
        ''', (id_conserve, id_doublon))
        
        # S'il y a des doublons qui n'ont pas pu être mis à jour (conflit d'unicité), 
        # on les supprime pour nettoyer
        cursor.execute('DELETE FROM RELEVES_PRIX WHERE magasin_id = ?', (id_doublon,))
        
        # 2. Mettre à jour le champ nomcsv du magasin conservé 
        # pour correspondre exactement au nom généré par le scraper
        cursor.execute('SELECT nom FROM MAGASINS WHERE id = ?', (id_doublon,))
        res = cursor.fetchone()
        if res:
            nom_nettoye = res[0]
            cursor.execute('UPDATE MAGASINS SET nomcsv = ? WHERE id = ?', (nom_nettoye, id_conserve))
            print(f"-> 'nomcsv' du magasin {id_conserve} mis à jour avec '{nom_nettoye}'")
        
        # 3. Supprimer le magasin doublon
        cursor.execute('DELETE FROM MAGASINS WHERE id = ?', (id_doublon,))
        print(f"-> Magasin doublon {id_doublon} supprimé.")

    conn.commit()
    conn.close()
    print("\n✅ Correction de la base de données terminée avec succès.")

if __name__ == "__main__":
    corriger_base()
