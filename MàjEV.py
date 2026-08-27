import sqlite3
import pandas as pd
from datetime import datetime


def exporter_differences_csv():
    """
    Exporte un fichier CSV avec les entrées de la base 2 qui diffèrent de la base 1
    """

    print("🔍 RECHERCHE DES DIFFÉRENCES ENTRE LES BASES")
    print("=" * 80)

    # Connexion aux bases de données
    conn1 = sqlite3.connect('EauVive_prix.db')
    conn2 = sqlite3.connect('EV_Tmp.db')

    try:
        # Lecture des tables
        df1 = pd.read_sql_query("SELECT * FROM PRODUITS", conn1)
        df2 = pd.read_sql_query("SELECT * FROM PRODUITS", conn2)

        print(f"📊 Base 1 (EauVive_prix.db) : {len(df1)} lignes")
        print(f"📊 Base 2 (AV_Tmpe.db)      : {len(df2)} lignes")
        print("=" * 80)

        # Trouver une colonne clé
        colonnes_cles = ['id', 'code', 'code_produit', 'reference']
        cle_principale = None

        for col in colonnes_cles:
            if col in df1.columns and col in df2.columns:
                cle_principale = col
                break

        if cle_principale is None:
            # Si pas de colonne clé, utiliser la première colonne commune
            cols_communes = list(set(df1.columns) & set(df2.columns))
            if cols_communes:
                cle_principale = cols_communes[0]
            else:
                print("❌ Aucune colonne commune trouvée entre les deux tables")
                return None

        print(f"🔑 Colonne clé utilisée : {cle_principale}")
        print("=" * 80)

        # 1. Identifier les produits présents dans les deux bases
        merged = pd.merge(df1, df2, on=cle_principale, how='inner',
                          suffixes=('_Base1', '_Base2'))

        print(f"\n📌 Produits présents dans les deux bases : {len(merged)}")

        # 2. Trouver les produits qui diffèrent
        lignes_differentes = []
        colonnes_modifiees = []

        for idx, row in merged.iterrows():
            differences = {}
            colonnes_diff = []

            for col in df1.columns:
                if col != cle_principale:
                    # Récupérer les valeurs des deux bases
                    val1 = row[f'{col}_Base1']
                    val2 = row[f'{col}_Base2']

                    # Comparer les valeurs (gérer les NaN)
                    if pd.isna(val1) and pd.isna(val2):
                        continue
                    elif pd.isna(val1) or pd.isna(val2):
                        differences[col] = {
                            'Base1': val1 if not pd.isna(val1) else 'NULL',
                            'Base2': val2 if not pd.isna(val2) else 'NULL'
                        }
                        colonnes_diff.append(col)
                    elif val1 != val2:
                        differences[col] = {
                            'Base1': val1,
                            'Base2': val2
                        }
                        colonnes_diff.append(col)

            if differences:
                # Créer une ligne avec toutes les colonnes de la base 2
                ligne_complete = {}
                for col in df2.columns:
                    if col == cle_principale:
                        ligne_complete[col] = row[col]
                    elif col in differences:
                        ligne_complete[col] = differences[col]['Base2']
                        ligne_complete[f'{col}_Base1'] = differences[col]['Base1']
                        ligne_complete[f'{col}_Differe'] = 'OUI'
                    else:
                        ligne_complete[col] = row[f'{col}_Base2']
                        ligne_complete[f'{col}_Base1'] = row[f'{col}_Base1']
                        ligne_complete[f'{col}_Differe'] = 'NON'

                ligne_complete['Nb_colonnes_modifiees'] = len(colonnes_diff)
                ligne_complete['Colonnes_modifiees'] = ', '.join(colonnes_diff)

                lignes_differentes.append(ligne_complete)
                colonnes_modifiees.extend(colonnes_diff)

        # 3. Créer le DataFrame des différences
        if lignes_differentes:
            df_diff = pd.DataFrame(lignes_differentes)

            # Réorganiser les colonnes pour une meilleure lisibilité
            cols_order = [cle_principale, 'Nb_colonnes_modifiees', 'Colonnes_modifiees']
            other_cols = [col for col in df_diff.columns if col not in cols_order]
            df_diff = df_diff[cols_order + other_cols]

            # Générer le nom du fichier
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            nom_fichier = f"produits_a_mettre_a_jour_{timestamp}.csv"

            # Exporter en CSV
            df_diff.to_csv(nom_fichier, index=False, encoding='utf-8-sig')

            print(f"\n✅ {len(lignes_differentes)} produits à mettre à jour")
            print(f"📁 Fichier généré : {nom_fichier}")

            # 4. Statistiques sur les colonnes modifiées
            print("\n📊 STATISTIQUES DES MODIFICATIONS")
            print("-" * 40)

            if colonnes_modifiees:
                from collections import Counter
                compteur = Counter(colonnes_modifiees)
                print("Colonnes les plus modifiées :")
                for col, count in compteur.most_common(10):
                    print(f"  {col:30} : {count} produits")

            # 5. Afficher un aperçu du fichier
            print("\n📋 APERÇU DU FICHIER (5 premières lignes)")
            print("-" * 40)
            print(df_diff.head(5).to_string(index=False))

            return nom_fichier

        else:
            print("\n✅ Aucune différence trouvée ! Les deux bases sont identiques.")
            return None

    except Exception as e:
        print(f"❌ Erreur : {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        conn1.close()
        conn2.close()


def exporter_nouveaux_produits():
    """
    Exporte les produits présents uniquement dans la base 2
    """

    conn1 = sqlite3.connect('EauVive_prix.db')
    conn2 = sqlite3.connect('AV_Tmpe.db')

    try:
        df1 = pd.read_sql_query("SELECT * FROM PRODUITS", conn1)
        df2 = pd.read_sql_query("SELECT * FROM PRODUITS", conn2)

        # Trouver la colonne clé
        colonnes_cles = ['id', 'code', 'code_produit', 'reference']
        cle = None
        for col in colonnes_cles:
            if col in df1.columns and col in df2.columns:
                cle = col
                break

        if cle is None:
            cols_communes = list(set(df1.columns) & set(df2.columns))
            cle = cols_communes[0] if cols_communes else None

        if cle:
            # Produits uniquement dans la base 2
            nouveaux = df2[~df2[cle].isin(df1[cle])]

            if len(nouveaux) > 0:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                nom_fichier = f"nouveaux_produits_base2_{timestamp}.csv"
                nouveaux.to_csv(nom_fichier, index=False, encoding='utf-8-sig')
                print(f"📁 Nouveaux produits exportés : {nom_fichier}")
                print(f"   ({len(nouveaux)} produits à ajouter)")
                return nom_fichier

    finally:
        conn1.close()
        conn2.close()


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("        EXPORT DES PRODUITS À METTRE À JOUR")
    print("=" * 80)

    # Exporter les différences
    fichier_diff = exporter_differences_csv()

    if fichier_diff:
        print("\n" + "=" * 80)
        print("📋 RÉSUMÉ DES FICHIERS GÉNÉRÉS")
        print("=" * 80)
        print(f"✅ Fichier principal : {fichier_diff}")
        print("   Contient toutes les entrées de la base 2 qui diffèrent de la base 1")
        print("   Avec pour chaque produit :")
        print("   - Toutes les colonnes de la base 2")
        print("   - Les valeurs correspondantes de la base 1")
        print("   - Un indicateur pour chaque colonne (Diffère OUI/NON)")
        print("   - Le nombre total de colonnes modifiées")
        print("   - La liste des colonnes modifiées")

        # Exporter aussi les nouveaux produits
        print("\n📁 Export des nouveaux produits...")
        exporter_nouveaux_produits()

        print("\n" + "=" * 80)
        print("💡 UTILISATION DU FICHIER CSV")
        print("=" * 80)
        print("1. Ouvrez le fichier CSV avec Excel ou un tableur")
        print("2. Les colonnes sont :")
        print("   - [clé] : l'identifiant du produit")
        print("   - Nb_colonnes_modifiees : nombre de colonnes à modifier")
        print("   - Colonnes_modifiees : liste des colonnes qui changent")
        print("   - [colonne]_Base1 : valeur dans EauVive_prix.db")
        print("   - [colonne] : valeur dans AV_Tmpe.db")
        print("   - [colonne]_Differe : OUI/NON selon si la colonne change")

    print("\n✅ Programme terminé")