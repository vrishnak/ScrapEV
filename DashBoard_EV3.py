# pyrefly: ignore [missing-import]
import streamlit as st
import pandas as pd
import sqlite3
# pyrefly: ignore [missing-import]
import plotly.express as px
import os
import urllib.parse
import streamlit.components.v1 as components

# Import du module de recherche
import sys
import re

def nettoyer_ean(valeur: str) -> str:
    """Nettoie un EAN collé : retire espaces, tirets, points, caractères invisibles."""
    if valeur is None:
        return ""
    # Garde uniquement les chiffres
    return re.sub(r"\D", "", str(valeur))


sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.recherche_EV import (
    gerer_recherche_nom,
    gerer_recherche_ean,
    gerer_recherche_code_interne,
    obtenir_info_produit,
    obtenir_historique_prix,
    obtenir_id_depuis_affichage,
    get_recherche_stats,
    enregistrer_ean,   # <-- AJOUT : fonction d'écriture
    DEBUG_EAN          # <-- AJOUT : flag global
)

# Configuration de la page
st.set_page_config(page_title="Dashboard EAU VIVE", page_icon="🛒", layout="wide")

# Custom CSS pour améliorer le design
st.markdown("""
<style>
    div[data-testid="metric-container"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .search-mode-info {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
        font-size: 0.9em;
    }
    .stCheckbox {
        margin: 5px 0;
    }
    /* Style des boutons radio de mode comme des "cartes" */
    div[role="radiogroup"] > label {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 6px;
        padding: 6px 12px;
        margin-right: 6px;
        cursor: pointer;
    }
    div[role="radiogroup"] > label:hover {
        background-color: #e9ecef;
    }
</style>
""", unsafe_allow_html=True)

DB_PATH = "EauVive_prix.db"


@st.cache_resource
def get_db_connection():
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH, check_same_thread=False)


conn = get_db_connection()

if conn is None:
    st.error(
        f"❌ Base de données introuvable ({DB_PATH}). Veuillez d'abord utiliser BDC_EauVive.py pour générer la base.")
    st.stop()

st.title("🛒 Tableau de Bord Analytique EAU VIVE")
st.markdown("Visualisation et comparaison de l'évolution des prix.")

# --- BARRE LATERALE : RECHERCHE ---
with st.sidebar:
    # --- BADGE MODE DEBUG EAN ---
    if DEBUG_EAN:
        st.markdown(
            '<div class="debug-badge debug-badge-on">'
            '✏️ Mode debug EAN : <strong>activé</strong>'
            '</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="debug-badge debug-badge-off">'
            '🔒 Mode debug EAN : <strong>désactivé</strong>'
            '</div>',
            unsafe_allow_html=True
        )
    st.header("🔍 Recherche de Produit")
    search_mode = st.radio("Mode de recherche", ["Nom (Mots-clés)", "Code EAN", "Code Interne"])
    st.divider()

    # Variables pour le mode de recherche par mots-clés
    mode_recherche_mots = "souple"  # par défaut
    selected_product_id = None

    if search_mode == "Nom (Mots-clés)":
        # --- OPTIONS DE RECHERCHE PAR MOTS-CLÉS ---
        # ✅ SOLUTION : st.radio horizontal => un seul mode actif, exclusion automatique.
        st.subheader("⚙️ Mode de recherche")

        mode_recherche_mots = st.radio(
            "Choisissez le mode :",
            options=["souple", "stricte"],
            format_func=lambda x: "🔓 Mode souple" if x == "souple" else "🔒 Mode strict",
            index=0,                # souple par défaut
            horizontal=True,
            key="mode_recherche_mots_radio",
            label_visibility="collapsed"
        )

        # Affichage pédagogique
        if mode_recherche_mots == "stricte":
            st.markdown("""
            <div class="search-mode-info">
                🔒 Mode <strong>strict</strong> : recherche exacte de la sous-chaîne<br>
                <span style="color: #6c757d; font-size: 0.85em;">
                    Ex: "Weleda crème" ne trouvera pas "crème Weleda"
                </span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="search-mode-info">
                🔓 Mode <strong>souple</strong> : recherche flexible (ordre indifférent)<br>
                <span style="color: #6c757d; font-size: 0.85em;">
                    Ex: "Weleda crème" trouvera "crème Weleda" et "crème de nuit Weleda"
                </span>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        # Champ de recherche
        search_query = st.text_input("Saisissez une partie du nom :", placeholder="ex: miel, chocolat...")

        if search_query:
            # Appel de la fonction de recherche avec le mode sélectionné
            df_search, _, display_list = gerer_recherche_nom(conn, search_query, mode_recherche_mots)

            if not df_search.empty:
                st.caption(f"🔍 {len(df_search)} résultat(s) trouvé(s)")

                if mode_recherche_mots == "souple" and 'score' in df_search.columns:
                    st.caption(f"🎯 Score moyen: {df_search['score'].mean():.1%}")

                selected_display = st.selectbox(
                    "Sélectionnez le produit exact :",
                    ["-- Choisissez un produit --"] + display_list
                )
                if selected_display != "-- Choisissez un produit --":
                    selected_product_id = obtenir_id_depuis_affichage(df_search, selected_display)
            else:
                st.warning("Aucun produit trouvé.")
                if mode_recherche_mots == "stricte" and len(search_query) > 3:
                    st.info("💡 Essayez le mode 'souple' pour une recherche plus flexible.")

    elif search_mode == "Code EAN":
        search_query = st.text_input("Saisissez l'EAN exact :", placeholder="ex: 3700000000000")
        if search_query:
            df_search, _, display_list = gerer_recherche_ean(conn, search_query)

            if not df_search.empty:
                selected_display = st.selectbox(
                    "Résultat(s) :",
                    ["-- Choisissez un produit --"] + display_list
                )
                if selected_display != "-- Choisissez un produit --":
                    selected_product_id = obtenir_id_depuis_affichage(df_search, selected_display)
            else:
                st.warning("EAN introuvable.")

    elif search_mode == "Code Interne":
        search_query = st.text_input("Saisissez le Code Interne exact :", placeholder="ex: 123456")
        if search_query:
            trouve, produit_id, description = gerer_recherche_code_interne(conn, search_query)
            if trouve:
                selected_product_id = produit_id
                st.success(f"Trouvé : {description}")
            else:
                st.warning("Code interne introuvable.")

    # --- STATISTIQUES DE LA BASE ---
    with st.sidebar.expander("📊 Statistiques de la base"):
        stats = get_recherche_stats(conn)
        st.metric("Total produits", stats['total_produits'])
        st.metric("Produits sans EAN", stats['sans_ean'])

        if not stats['top_marques'].empty:
            st.write("Top 5 marques:")
            for _, row in stats['top_marques'].head(5).iterrows():
                st.write(f"- {row['marque']}: {row['count']}")

# --- CONTENU PRINCIPAL : AFFICHAGE DES DONNEES ---
if selected_product_id:
    # Récupération des infos du produit
    df_prod = obtenir_info_produit(conn, selected_product_id)

    if not df_prod.empty:
        prod_info = df_prod.iloc[0]
        st.header(f"📦 {prod_info['description']}")

        # Affichage des tags d'information
        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        col_t1.info(f"**Code Interne:** {prod_info['code_interne']}")
        col_t2.info(f"**EAN:** {prod_info['ean'] if prod_info['ean'] else 'N/A'}")
        col_t3.info(f"**Marque:** {prod_info['marque'] if prod_info['marque'] else 'N/A'}")
        col_t4.info(f"**Volume:** {prod_info['volume'] if prod_info['volume'] else 'N/A'}")

        st.divider()

        # --- FORMULAIRE D'ENREGISTREMENT EAN (uniquement si DEBUG_EAN == True) ---
        if DEBUG_EAN:
            with st.expander("✏️ Enregistrer / Modifier l'EAN de ce produit", expanded=False):
                ean_actuel = str(prod_info['ean']) if pd.notna(prod_info['ean']) else ""

                st.caption(
                    "💡 Astuce : vous pouvez **coller** un EAN directement avec **CTRL+V** "
                    "(les espaces, tirets et retours à la ligne sont nettoyés automatiquement)."
                )

                with st.form(key=f"form_ean_{selected_product_id}"):
                    # ⚠️ On retire max_chars pour ne pas tronquer un collage "sale"
                    #     La validation se fait après nettoyage.
                    ean_saisi = st.text_input(
                        "EAN (8, 12 ou 13 chiffres) — collez avec CTRL+V",
                        value=ean_actuel,
                        placeholder="Collez ou tapez l'EAN ici…",
                        help="Le collage est autorisé. Espaces et tirets seront retirés automatiquement.",
                        autocomplete="off",
                        key=f"input_ean_{selected_product_id}"
                    )

                    # Aperçu live du nettoyage (utile pour voir ce qui sera enregistré)
                    ean_clean_preview = nettoyer_ean(ean_saisi)
                    if ean_saisi and ean_clean_preview != ean_saisi:
                        st.info(f"🧹 Nettoyé : `{ean_clean_preview}`")

                    col_save, _ = st.columns([1, 3])
                    with col_save:
                        submit = st.form_submit_button("💾 Enregistrer", use_container_width=True)

                if submit:
                    ean_clean = nettoyer_ean(ean_saisi)

                    # Validation après nettoyage
                    if ean_clean and len(ean_clean) not in (8, 12, 13):
                        st.error(
                            f"⚠️ EAN invalide après nettoyage : `{ean_clean}` "
                            f"({len(ean_clean)} chiffres). Attendu : 8, 12 ou 13 chiffres."
                        )
                    else:
                        ok, msg = enregistrer_ean(
                            conn,
                            selected_product_id,
                            ean_clean if ean_clean else None
                        )
                        if ok:
                            st.success(msg)
                            st.cache_resource.clear()
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(msg)
        # --- BOUTON RECHERCHE EAN & FICHE PRODUIT ---
        query = urllib.parse.quote(f"{prod_info['description']} AND (ean OR gtin)")
        google_url = f"https://www.google.com/search?q={query}"
        fiche_url = prod_info['lien_fiche'] if 'lien_fiche' in prod_info and pd.notna(prod_info['lien_fiche']) else ""

        if fiche_url:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.link_button("🔍 Rechercher EAN sur Google", google_url, width='stretch')
            with col_b2:
                st.link_button("🌐 Ouvrir Fiche Produit", fiche_url, width='stretch')
        else:
            st.link_button("🔍 Rechercher EAN sur Google", google_url, width='stretch')

        st.divider()

        # Récupération de l'historique des prix
        df_prix = obtenir_historique_prix(conn, selected_product_id)

        if not df_prix.empty:
            df_prix['prix_num'] = pd.to_numeric(
                df_prix['prix'].astype(str).str.replace(',', '.', regex=False),
                errors='coerce'
            )

            # --- KPI ---
            st.subheader("📊 Indicateurs Clés")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Prix Minimum", f"{df_prix['prix_num'].min():.2f} €")
            col2.metric("Prix Maximum", f"{df_prix['prix_num'].max():.2f} €")
            col3.metric("Prix Moyen", f"{df_prix['prix_num'].mean():.2f} €")
            col4.metric("Nombre de relevés", len(df_prix))

            st.markdown("<br>", unsafe_allow_html=True)

            # --- GRAPHIQUES ---
            tab1, tab2 = st.tabs(["📈 Évolution dans le temps", "⚖️ Comparaison des magasins"])

            with tab1:
                fig_line = px.line(
                    df_prix,
                    x="date_releve",
                    y="prix_num",
                    color="magasin",
                    markers=True,
                    title="Historique des prix par magasin",
                    labels={"prix_num": "Prix (€)", "date_releve": "Date du relevé", "magasin": "Magasin"},
                    template="plotly_white"
                )
                fig_line.update_layout(yaxis_tickformat='.2f')
                st.plotly_chart(fig_line, use_container_width=True)

            with tab2:
                df_latest = df_prix.sort_values('date_releve').drop_duplicates('magasin', keep='last')
                df_latest = df_latest.sort_values('prix_num')

                fig_bar = px.bar(
                    df_latest,
                    x="magasin",
                    y="prix_num",
                    text="prix_num",
                    color="magasin",
                    title="Derniers prix relevés par magasin",
                    labels={"prix_num": "Prix (€)", "magasin": "Magasin"},
                    template="plotly_white"
                )
                fig_bar.update_traces(texttemplate='%{text:.2f} €', textposition='outside')
                fig_bar.update_layout(uniformtext_minsize=8, uniformtext_mode='hide', yaxis_tickformat='.2f')
                st.plotly_chart(fig_bar, use_container_width=True)

                st.caption(
                    "Remarque : Ce graphique affiche le dernier prix connu pour chaque magasin, même si les dates de relevé diffèrent d'un magasin à l'autre.")

            # --- TABLEAU DE DONNEES BRUTES ---
            st.divider()
            with st.expander("Voir les données brutes"):
                st.dataframe(
                    df_prix[['date_releve', 'magasin', 'prix', 'prix_old', 'prix_unit']].sort_values('date_releve',
                                                                                                     ascending=False),
                    use_container_width=True)

        else:
            st.info("Aucun relevé de prix n'a encore été enregistré pour ce produit dans la base de données.")

else:
    st.markdown("""
        <div style="text-align: center; padding: 50px;">
            <h2 style="color: #6c757d;">Bienvenue sur votre Dashboard</h2>
            <p style="font-size: 18px;">Utilisez le panneau latéral gauche pour rechercher un produit et analyser l'évolution de ses prix.</p>
            <p style="font-size: 16px; color: #6c757d;">
                💡 Astuce : Utilisez le <strong>mode souple</strong> pour des recherches flexibles (ordre indifférent).
            </p>
        </div>
    """, unsafe_allow_html=True)