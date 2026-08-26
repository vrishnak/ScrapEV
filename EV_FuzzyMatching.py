import sqlite3
from rapidfuzz import fuzz
import re
import unicodedata
from collections import Counter
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import tempfile
import os
import sys
import datetime

DB_PATH = "EauVive_prix.db"


def normaliser_texte(texte):
    if texte is None:
        return ""

    # Conversion en minuscules
    texte = str(texte).lower()

    # Suppression des accents
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))

    # On remplace les séparateurs/ponctuations par des espaces,
    # SAUF les virgules et les points.
    texte = re.sub(r"[-_/;:!?()+\[\]{}]+", " ", texte)

    # On conserve :
    # - lettres a-z
    # - chiffres 0-9
    # - espaces
    # - points
    # - virgules
    texte = re.sub(r"[^a-z0-9\s.,]", "", texte)

    # On remplace plusieurs espaces par un seul
    texte = re.sub(r"\s+", " ", texte).strip()

    return texte


def calculer_score(desc1, desc2):
    d1 = normaliser_texte(desc1)
    d2 = normaliser_texte(desc2)

    if not d1 or not d2:
        return 0

    tokens1 = d1.split()
    tokens2 = d2.split()

    if not tokens1 or not tokens2:
        return 0

    # Similarité globale sur le texte
    score_texte = fuzz.token_sort_ratio(d1, d2) / 100.0

    # Score de correspondance des mots
    counter1 = Counter(tokens1)
    counter2 = Counter(tokens2)

    mots_communs = sum((counter1 & counter2).values())
    mots_total = max(len(tokens1), len(tokens2))

    if mots_total == 0:
        return 0

    score_mots = mots_communs / mots_total

    # Score final entre 0 et 1000
    score_final = score_texte * score_mots

    return int(round(score_final * 1000))


def supprimer_lignes_score_inferieur_400(conn):
    """
    Relit la table RESULTATS_RECHERCHE,
    sélectionne les lignes ayant desc_score < 400,
    puis les supprime.
    """
    cursor = conn.cursor()

    # Relecture de la table pour trouver les lignes à supprimer
    cursor.execute("""
        SELECT rowid
        FROM RESULTATS_RECHERCHE
        WHERE desc_score < 400
    """)

    rowids_a_supprimer = [row[0] for row in cursor.fetchall()]

    # Suppression effective
    if rowids_a_supprimer:
        cursor.executemany("""
            DELETE FROM RESULTATS_RECHERCHE
            WHERE rowid = ?
        """, [(rowid,) for rowid in rowids_a_supprimer])

        conn.commit()

    return len(rowids_a_supprimer)


def mettre_a_jour_scores():
    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        # Sélection des lignes à traiter
        cursor.execute("""
            SELECT rowid, description_originale, description_h2
            FROM RESULTATS_RECHERCHE
        """)

        rows = cursor.fetchall()

        updates = []

        for rowid, desc_originale, desc_h2 in rows:
            score = calculer_score(desc_originale, desc_h2)
            updates.append((score, rowid))

        # Mise à jour en lot
        cursor.executemany("""
            UPDATE RESULTATS_RECHERCHE
            SET desc_score = ?
            WHERE rowid = ?
        """, updates)

        conn.commit()

        print(f"Mise à jour terminée : {len(updates)} lignes traitées.")

        # Suppression des lignes ayant un score inférieur à 400
        nb_supprimees = supprimer_lignes_score_inferieur_400(conn)

        print(f"Suppression terminée : {nb_supprimees} lignes avec desc_score < 400 supprimées.")

    finally:
        conn.close()


def lancer_interface_validation():
    root = tk.Tk()
    root.title("Validation des Correspondances (Score 1000)")
    root.geometry("1200x600")

    # Cadre supérieur (Boutons)
    top_frame = tk.Frame(root)
    top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

    # Cadre principal (Tableau)
    main_frame = tk.Frame(root)
    main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

    # Scrollbars
    scrollbar_y = tk.Scrollbar(main_frame, orient=tk.VERTICAL)
    scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)

    scrollbar_x = tk.Scrollbar(main_frame, orient=tk.HORIZONTAL)
    scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)

    # Tableau (Treeview)
    columns = ("select", "code_interne", "desc_produit", "desc_recherche", "ean", "lien_fiche", "lien_href")
    tree = ttk.Treeview(main_frame, columns=columns, show="headings",
                        yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set, selectmode="extended")
    
    tree.heading("select", text="[ ] Tout")
    tree.heading("code_interne", text="Code Interne")
    tree.heading("desc_produit", text="Description PRODUIT")
    tree.heading("desc_recherche", text="Description RECHERCHE")
    tree.heading("ean", text="EAN Trouvé")
    tree.heading("lien_fiche", text="Lien Fiche")
    tree.heading("lien_href", text="Lien Recherche")

    tree.column("select", width=80, stretch=tk.NO, anchor=tk.CENTER)
    tree.column("code_interne", width=100, stretch=tk.NO)
    tree.column("desc_produit", width=250)
    tree.column("desc_recherche", width=250)
    tree.column("ean", width=120, stretch=tk.NO)
    tree.column("lien_fiche", width=200)
    tree.column("lien_href", width=200)

    def toggle_check(event):
        region = tree.identify("region", event.x, event.y)
        if region == "heading":
            column = tree.identify_column(event.x)
            if column == '#1':
                current = tree.heading('#1')['text']
                if current == "[ ] Tout":
                    tree.heading('#1', text="[X] Tout")
                    new_val = "✅"
                else:
                    tree.heading('#1', text="[ ] Tout")
                    new_val = "🔲"
                
                for item in tree.get_children():
                    vals = list(tree.item(item, "values"))
                    vals[0] = new_val
                    tree.item(item, values=vals)
        elif region == "cell":
            column = tree.identify_column(event.x)
            if column == '#1':
                item = tree.identify_row(event.y)
                if item:
                    vals = list(tree.item(item, "values"))
                    vals[0] = "✅" if vals[0] == "🔲" else "🔲"
                    tree.item(item, values=vals)

    tree.bind('<ButtonRelease-1>', toggle_check)

    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    scrollbar_y.config(command=tree.yview)
    scrollbar_x.config(command=tree.xview)

    def load_data():
        # Vider le tableau
        for item in tree.get_children():
            tree.delete(item)

        if not os.path.exists(DB_PATH):
            messagebox.showerror("Erreur", f"Le fichier de base de données {DB_PATH} est introuvable.")
            return

        conn = sqlite3.connect(DB_PATH)
        try:
            cursor = conn.cursor()
            # On cherche les produits dont le score est 1000
            query = """
                SELECT r.code_interne, p.description, r.description_h2, r.ean, p.lien_fiche, r.lien_href
                FROM RESULTATS_RECHERCHE r
                JOIN PRODUITS p ON r.code_interne = p.code_interne
                WHERE r.desc_score = 1000
                GROUP BY r.code_interne
            """
            cursor.execute(query)
            rows = cursor.fetchall()

            for row in rows:
                tree.insert("", tk.END, values=("🔲",) + row)

        except Exception as e:
            messagebox.showerror("Erreur Base de Données", str(e))
        finally:
            conn.close()

    def compare_products():
        selected_items = tree.selection()
        if not selected_items:
            messagebox.showwarning("Attention", "Veuillez sélectionner une ligne pour comparer.")
            return

        # On prend la première ligne sélectionnée
        item = selected_items[0]
        values = tree.item(item, "values")
        
        lien_fiche = values[5]
        lien_href = values[6]

        if not lien_fiche or not lien_href:
            messagebox.showwarning("Attention", "Les liens sont manquants pour cette ligne.")
            return

        # Création du fichier HTML avec deux iframes
        html_content = f"""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <title>Comparaison des produits</title>
            <style>
                body {{ margin: 0; padding: 0; display: flex; height: 100vh; font-family: sans-serif; }}
                .container {{ flex: 1; display: flex; flex-direction: column; border: 1px solid #ccc; }}
                .header {{ background: #f0f0f0; padding: 10px; text-align: center; border-bottom: 1px solid #ccc; word-wrap: break-word; }}
                .header a {{ color: #0066cc; text-decoration: none; }}
                iframe {{ flex: 1; border: none; width: 100%; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <strong>PRODUIT (Fiche)</strong><br>
                    <a href="{lien_fiche}" target="_blank">{lien_fiche}</a>
                </div>
                <iframe src="{lien_fiche}"></iframe>
            </div>
            <div class="container">
                <div class="header">
                    <strong>RECHERCHE (Résultat)</strong><br>
                    <a href="{lien_href}" target="_blank">{lien_href}</a>
                </div>
                <iframe src="{lien_href}"></iframe>
            </div>
        </body>
        </html>
        """

        fd, path = tempfile.mkstemp(suffix=".html", prefix="compare_produits_")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # Ouverture dans le navigateur
        webbrowser.open('file://' + os.path.realpath(path))

    def validate_selection():
        items_to_update = []
        for item in tree.get_children():
            values = tree.item(item, "values")
            if values[0] == "✅":
                items_to_update.append(item)

        if not items_to_update:
            messagebox.showwarning("Attention", "Veuillez cocher (🔲 -> ✅) au moins une ligne à valider.")
            return

        if not messagebox.askyesno("Confirmation", f"Voulez-vous vraiment mettre à jour l'EAN pour les {len(items_to_update)} produits cochés ?"):
            return

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        updates = []
        deletes = []
        for item in items_to_update:
            values = tree.item(item, "values")
            code_interne = values[1]
            ean = values[4]
            updates.append((ean, today, code_interne))
            deletes.append((code_interne,))

        if not updates:
            return

        conn = sqlite3.connect(DB_PATH)
        try:
            cursor = conn.cursor()
            # Mise à jour de la table PRODUITS
            cursor.executemany("""
                UPDATE PRODUITS
                SET ean = ?, date_validation = ?
                WHERE code_interne = ?
            """, updates)
            
            # Suppression dans la table RESULTATS_RECHERCHE
            cursor.executemany("""
                DELETE FROM RESULTATS_RECHERCHE
                WHERE code_interne = ?
            """, deletes)
            
            conn.commit()
            messagebox.showinfo("Succès", f"{len(updates)} produits mis à jour et supprimés de la recherche avec succès.")
            
            # Supprimer les lignes validées du tableau
            for item in items_to_update:
                tree.delete(item)

        except Exception as e:
            conn.rollback()
            messagebox.showerror("Erreur", f"Erreur lors de la mise à jour: {str(e)}")
        finally:
            conn.close()

    btn_compare = tk.Button(top_frame, text="Comparer les produits (Navigateur)", command=compare_products)
    btn_compare.pack(side=tk.LEFT, padx=5)

    btn_validate = tk.Button(top_frame, text="Valider la sélection (Mettre à jour EAN)", command=validate_selection, bg="lightgreen")
    btn_validate.pack(side=tk.LEFT, padx=5)

    btn_refresh = tk.Button(top_frame, text="Actualiser", command=load_data)
    btn_refresh.pack(side=tk.RIGHT, padx=5)

    # Charger les données initiales
    load_data()

    root.mainloop()


if __name__ == "__main__":
    if "--gui" in sys.argv:
        lancer_interface_validation()
    else:
        mettre_a_jour_scores()
        print("\nPour lancer l'interface graphique de validation, utilisez la commande :")
        print("python EV_FuzzyMatching.py --gui")