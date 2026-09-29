import os
import json
import glob
import re
from datetime import datetime
from collections import defaultdict
import pandas as pd

# Pour lancer l'interface web, exécutez dans le terminal :
# streamlit run ETUDE_PATE.py
try:
    import streamlit as st
except ImportError:
    print("Veuillez installer streamlit : pip install streamlit")
    exit(1)

st.set_page_config(page_title="Étude Pâtes", layout="wide")

JSON_DIR = os.path.join("DATA_EV", "JSON")
GLOBAL_JSON_PATH = os.path.join(JSON_DIR, "global_pates.json")
GROUPES_JSON_PATH = os.path.join(JSON_DIR, "groupes_pates.json")

def extraire_magasin(filename):
    # Format attendu : V5_{magasin}_{date}_{famille}.json
    # Exemple : V5_Annecy_260928_Epicerie_Pates.json
    m = re.match(r"V5_(.+?)_\d+_.+\.json", filename)
    if m:
        return m.group(1)
    return filename

def generer_fichier_global():
    # Trouver tous les fichiers du jour ou récents pour les pâtes
    # On va prendre tous les fichiers contenant "Pates" dans le nom
    fichiers_pates = glob.glob(os.path.join(JSON_DIR, "*_Pates.json"))
    
    donnees_globales = []
    
    for filepath in fichiers_pates:
        filename = os.path.basename(filepath)
        magasin = extraire_magasin(filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                produits = json.load(f)
                for prod in produits:
                    prod['magasin_source'] = magasin
                donnees_globales.extend(produits)
        except Exception as e:
            st.error(f"Erreur lors de la lecture de {filename}: {e}")
            
    if donnees_globales:
        with open(GLOBAL_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(donnees_globales, f, ensure_ascii=False, indent=4)
        return donnees_globales, [extraire_magasin(os.path.basename(f)) for f in fichiers_pates]
    return [], []

def analyser_references(donnees_globales, liste_magasins):
    ref_dict = defaultdict(lambda: {"produit": None, "magasins": set()})
    
    for prod in donnees_globales:
        ref_id = prod.get("ref_id")
        if ref_id:
            if not ref_dict[ref_id]["produit"]:
                # Conserver les infos du premier produit trouvé
                ref_dict[ref_id]["produit"] = {
                    "ref_id": ref_id,
                    "description": prod.get("description", ""),
                    "marque": prod.get("marque", ""),
                    "volume": prod.get("volume", ""),
                    "prix": prod.get("prix", ""),
                    "lien": prod.get("lien", "")
                }
            ref_dict[ref_id]["magasins"].add(prod["magasin_source"])
            
    nb_magasins_total = len(set(liste_magasins))
    
    tronc_commun = []
    restant = []
    
    for ref_id, data in ref_dict.items():
        # Si la référence est présente dans tous les magasins (ou presque), c'est le tronc commun
        # On peut définir une règle : présent dans au moins 80% des magasins, ou 100%
        if len(data["magasins"]) == nb_magasins_total and nb_magasins_total > 0:
            tronc_commun.append(data)
        else:
            restant.append(data)
            
    return tronc_commun, restant

def main():
    st.title("🍝 Analyse et Regroupement des Pâtes")
    
    st.sidebar.header("Actions")
    if st.sidebar.button("Générer le fichier global JSON"):
        with st.spinner("Génération en cours..."):
            donnees, magasins = generer_fichier_global()
            if donnees:
                st.sidebar.success(f"Fichier global généré avec {len(donnees)} produits provenant de {len(magasins)} fichiers/magasins.")
            else:
                st.sidebar.warning("Aucune donnée trouvée.")
                
    # Charger les données globales si elles existent
    if os.path.exists(GLOBAL_JSON_PATH):
        with open(GLOBAL_JSON_PATH, 'r', encoding='utf-8') as f:
            donnees_globales = json.load(f)
            
        magasins_uniques = list(set([p.get("magasin_source") for p in donnees_globales if "magasin_source" in p]))
        
        tronc_commun, restant = analyser_references(donnees_globales, magasins_uniques)
        
        st.header(f"🌳 Tronc Commun ({len(tronc_commun)} références)")
        st.write(f"Références présentes dans **tous** les magasins ({len(magasins_uniques)} magasins).")
        
        if tronc_commun:
            df_tronc = pd.DataFrame([
                {
                    "Réf": item["produit"]["ref_id"],
                    "Description": item["produit"]["description"],
                    "Volume": item["produit"]["volume"],
                    "Prix": item["produit"]["prix"],
                    "Présent dans": ", ".join(item["magasins"])
                } for item in tronc_commun
            ])
            st.dataframe(df_tronc, use_container_width=True)
            
        st.header(f"🧩 Références Restantes ({len(restant)} références)")
        st.write("Catégorisez ces références dans l'un des 3 groupes.")
        
        # Charger les groupes existants
        groupes_sauves = {}
        if os.path.exists(GROUPES_JSON_PATH):
            with open(GROUPES_JSON_PATH, 'r', encoding='utf-8') as f:
                groupes_sauves = json.load(f)
                
        # Préparation des données pour le DataFrame modifiable
        lignes_restantes = []
        for item in restant:
            ref_id = item["produit"]["ref_id"]
            groupe_actuel = groupes_sauves.get(ref_id, "Non assigné")
            
            lignes_restantes.append({
                "Réf": ref_id,
                "Description": item["produit"]["description"],
                "Nb Magasins": len(item["magasins"]),
                "Magasins": ", ".join(item["magasins"]),
                "Groupe": groupe_actuel
            })
            
        df_restant = pd.DataFrame(lignes_restantes)
        
        if not df_restant.empty:
            # Interface de modification des groupes
            st.subheader("Assignation des groupes")
            
            # Utilisation de st.data_editor pour modifier la colonne 'Groupe'
            edited_df = st.data_editor(
                df_restant,
                column_config={
                    "Groupe": st.column_config.SelectboxColumn(
                        "Assigner au groupe",
                        help="Choisissez un groupe",
                        options=["Non assigné", "Groupe 1", "Groupe 2", "Groupe 3"],
                        required=True,
                    ),
                    "Magasins": st.column_config.TextColumn("Magasins", width="large")
                },
                disabled=["Réf", "Description", "Nb Magasins", "Magasins"],
                hide_index=True,
                use_container_width=True
            )
            
            if st.button("💾 Sauvegarder les groupes"):
                # Mettre à jour le dictionnaire des groupes
                nouveaux_groupes = {}
                for index, row in edited_df.iterrows():
                    if row["Groupe"] != "Non assigné":
                        nouveaux_groupes[row["Réf"]] = row["Groupe"]
                        
                with open(GROUPES_JSON_PATH, 'w', encoding='utf-8') as f:
                    json.dump(nouveaux_groupes, f, ensure_ascii=False, indent=4)
                st.success("Les groupes ont été sauvegardés avec succès !")
                
            # Afficher un résumé des groupes
            st.subheader("📊 Résumé des groupes")
            col1, col2, col3 = st.columns(3)
            g1 = len(edited_df[edited_df["Groupe"] == "Groupe 1"])
            g2 = len(edited_df[edited_df["Groupe"] == "Groupe 2"])
            g3 = len(edited_df[edited_df["Groupe"] == "Groupe 3"])
            
            col1.metric("Groupe 1", g1)
            col2.metric("Groupe 2", g2)
            col3.metric("Groupe 3", g3)

    else:
        st.info("Le fichier global n'existe pas encore. Veuillez le générer via le menu de gauche.")

if __name__ == "__main__":
    main()
