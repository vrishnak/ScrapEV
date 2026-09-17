"""
Micro-programme : suppression d'un produit de la base EauVive_prix.db

Fonctionnalités :
  - Recherche par code interne, EAN ou mot-clé dans la description
  - Affichage des informations du produit
  - Visualisation des relations (relevés de prix, conflits EAN)
  - Suppression avec confirmation et nettoyage en cascade
"""

import sqlite3
import os
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime


DB_PATH_DEFAUT = "EauVive_prix.db"


# =====================================================================
#  COUCHE BASE DE DONNÉES
# =====================================================================
class SuppressionDB:
    """Accès ciblé à la base pour la suppression d'un produit."""

    def __init__(self, db_path=DB_PATH_DEFAUT):
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Base introuvable : {db_path}")
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    # ------------------------------------------------------------------
    #  Recherche
    # ------------------------------------------------------------------
    def rechercher(self, terme):
        """Recherche les produits contenant `terme` dans code_interne,
        EAN ou description. Retourne une liste de Row."""
        terme = f"%{terme.strip()}%"
        self.cursor.execute('''
            SELECT p.id, p.code_interne, p.ean, p.description,
                   p.marque, p.volume, p.lien_fiche, p.caracteristique,
                   p.url_img, p.categorie_id, p.ean_valide,
                   p.date_validation,
                   c.nom AS categorie_nom
            FROM PRODUITS p
            LEFT JOIN CATEGORIES c ON c.id = p.categorie_id
            WHERE p.code_interne LIKE ?
               OR p.ean LIKE ?
               OR p.description LIKE ?
            ORDER BY p.description
            LIMIT 200
        ''', (terme, terme, terme))
        return self.cursor.fetchall()

    def get_produit(self, produit_id):
        """Récupère un produit par son id."""
        self.cursor.execute('''
            SELECT p.*, c.nom AS categorie_nom
            FROM PRODUITS p
            LEFT JOIN CATEGORIES c ON c.id = p.categorie_id
            WHERE p.id = ?
        ''', (produit_id,))
        return self.cursor.fetchone()

    # ------------------------------------------------------------------
    #  Relations
    # ------------------------------------------------------------------
    def get_releves_prix(self, produit_id):
        """Récupère tous les relevés de prix d'un produit."""
        self.cursor.execute('''
            SELECT r.id, r.date_releve, r.prix, r.prix_old, r.prix_unit,
                   m.nom AS magasin_nom
            FROM RELEVES_PRIX r
            LEFT JOIN MAGASINS m ON m.id = r.magasin_id
            WHERE r.produit_id = ?
            ORDER BY r.date_releve DESC
        ''', (produit_id,))
        return self.cursor.fetchall()

    def get_conflits_ean(self, code_interne):
        """Récupère les conflits EAN liés à un code_interne."""
        self.cursor.execute('''
            SELECT c.id, c.ean, c.code_interne_1, c.code_interne_2,
                   c.date_detection, c.statut, c.commentaire
            FROM CONFLITS_EAN c
            WHERE c.code_interne_1 = ? OR c.code_interne_2 = ?
            ORDER BY c.date_detection DESC
        ''', (code_interne, code_interne))
        return self.cursor.fetchall()

    # ------------------------------------------------------------------
    #  Suppression
    # ------------------------------------------------------------------
    def supprimer_produit(self, produit_id):
        """Supprime un produit et ses dépendances :
             - RELEVES_PRIX liés
             - CONFLITS_EAN liés
             - Le produit lui-même
        Le tout dans une transaction. Retourne un dict de statistiques.
        """
        prod = self.get_produit(produit_id)
        if not prod:
            return None

        code_interne = prod['code_interne']
        stats = {'releves': 0, 'conflits': 0, 'produit': 0}

        try:
            self.cursor.execute("BEGIN")

            # 1. Supprimer les relevés de prix
            self.cursor.execute(
                "DELETE FROM RELEVES_PRIX WHERE produit_id = ?",
                (produit_id,)
            )
            stats['releves'] = self.cursor.rowcount

            # 2. Supprimer les conflits EAN
            self.cursor.execute('''
                DELETE FROM CONFLITS_EAN
                WHERE code_interne_1 = ? OR code_interne_2 = ?
            ''', (code_interne, code_interne))
            stats['conflits'] = self.cursor.rowcount

            # 3. Supprimer le produit
            self.cursor.execute(
                "DELETE FROM PRODUITS WHERE id = ?",
                (produit_id,)
            )
            stats['produit'] = self.cursor.rowcount

            self.conn.commit()
            return stats

        except Exception as e:
            self.conn.rollback()
            raise e

    def fermer(self):
        if self.conn:
            self.conn.close()


# =====================================================================
#  INTERFACE GRAPHIQUE
# =====================================================================
class FenetreSuppression:
    def __init__(self, root, db_path=DB_PATH_DEFAUT):
        self.root = root
        self.root.title("Suppression de produit — Catalogue Eau Vive")
        self.root.geometry("950x700")

        try:
            self.db = SuppressionDB(db_path)
        except FileNotFoundError as e:
            messagebox.showerror("Base introuvable", str(e))
            self.root.destroy()
            return

        self.produit_selectionne = None  # Row du produit affiché

        self._creer_interface()

    # ------------------------------------------------------------------
    #  Construction de l'interface
    # ------------------------------------------------------------------
    def _creer_interface(self):
        # Frame principal
        main = ttk.Frame(self.root, padding="10")
        main.pack(fill=tk.BOTH, expand=True)

        # --- Barre de recherche ---
        search_frame = ttk.LabelFrame(main, text="🔍 Recherche", padding="10")
        search_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(search_frame, text="Code interne, EAN ou mot-clé :").pack(side=tk.LEFT, padx=5)

        self.entry_recherche = ttk.Entry(search_frame, width=50)
        self.entry_recherche.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.entry_recherche.bind("<Return>", lambda e: self.lancer_recherche())

        ttk.Button(
            search_frame, text="Rechercher",
            command=self.lancer_recherche
        ).pack(side=tk.LEFT, padx=5)

        # --- Panneau principal : liste à gauche, détails à droite ---
        paned = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Colonne gauche : résultats
        left = ttk.LabelFrame(paned, text="Résultats", padding="5")
        paned.add(left, weight=1)

        cols = ("code", "ean", "description")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=20)
        self.tree.heading("code", text="Code interne")
        self.tree.heading("ean", text="EAN")
        self.tree.heading("description", text="Description")
        self.tree.column("code", width=80, anchor=tk.W)
        self.tree.column("ean", width=110, anchor=tk.W)
        self.tree.column("description", width=280, anchor=tk.W)

        tree_scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self.on_selection_produit)

        # Colonne droite : détails
        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        # Infos produit
        info_frame = ttk.LabelFrame(right, text="📦 Produit", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))

        self.labels_info = {}
        champs = [
            ('code_interne',   'Code interne'),
            ('ean',            'EAN'),
            ('description',    'Description'),
            ('marque',         'Marque'),
            ('volume',         'Volume'),
            ('categorie_nom',  'Catégorie'),
            ('lien_fiche',     'Lien fiche'),
            ('caracteristique','Caractéristiques'),
            ('url_img',        'URL image'),
        ]
        for i, (cle, libelle) in enumerate(champs):
            ttk.Label(info_frame, text=f"{libelle} :", font=('Arial', 9, 'bold')).grid(
                row=i, column=0, sticky=tk.NW, padx=5, pady=2
            )
            val = ttk.Label(info_frame, text="—", wraplength=380, justify=tk.LEFT)
            val.grid(row=i, column=1, sticky=tk.W, padx=5, pady=2)
            self.labels_info[cle] = val

        # Relevés de prix
        releves_frame = ttk.LabelFrame(right, text="💰 Relevés de prix", padding="10")
        releves_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        cols_r = ("date", "magasin", "prix", "prix_old", "prix_unit")
        self.tree_releves = ttk.Treeview(releves_frame, columns=cols_r,
                                         show="headings", height=6)
        self.tree_releves.heading("date", text="Date")
        self.tree_releves.heading("magasin", text="Magasin")
        self.tree_releves.heading("prix", text="Prix")
        self.tree_releves.heading("prix_old", text="Anc. prix")
        self.tree_releves.heading("prix_unit", text="Prix unitaire")
        self.tree_releves.column("date", width=90)
        self.tree_releves.column("magasin", width=120)
        self.tree_releves.column("prix", width=70)
        self.tree_releves.column("prix_old", width=70)
        self.tree_releves.column("prix_unit", width=100)

        scroll_r = ttk.Scrollbar(releves_frame, orient=tk.VERTICAL,
                                 command=self.tree_releves.yview)
        self.tree_releves.configure(yscrollcommand=scroll_r.set)
        self.tree_releves.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_r.pack(side=tk.RIGHT, fill=tk.Y)

        # Conflits EAN
        conflits_frame = ttk.LabelFrame(right, text="⚠️ Conflits EAN", padding="10")
        conflits_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        cols_c = ("ean", "autre", "date", "statut")
        self.tree_conflits = ttk.Treeview(conflits_frame, columns=cols_c,
                                          show="headings", height=4)
        self.tree_conflits.heading("ean", text="EAN")
        self.tree_conflits.heading("autre", text="Autre code interne")
        self.tree_conflits.heading("date", text="Détection")
        self.tree_conflits.heading("statut", text="Statut")
        self.tree_conflits.column("ean", width=110)
        self.tree_conflits.column("autre", width=120)
        self.tree_conflits.column("date", width=90)
        self.tree_conflits.column("statut", width=100)

        scroll_c = ttk.Scrollbar(conflits_frame, orient=tk.VERTICAL,
                                 command=self.tree_conflits.yview)
        self.tree_conflits.configure(yscrollcommand=scroll_c.set)
        self.tree_conflits.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_c.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Boutons d'action ---
        action_frame = ttk.Frame(main)
        action_frame.pack(fill=tk.X, pady=10)

        self.btn_supprimer = ttk.Button(
            action_frame,
            text="🗑️  Supprimer ce produit",
            command=self.supprimer_produit_selectionne,
            state='disabled'
        )
        self.btn_supprimer.pack(side=tk.LEFT, padx=5)

        ttk.Button(
            action_frame,
            text="🔄 Rafraîchir la recherche",
            command=self.lancer_recherche
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            action_frame,
            text="❌ Fermer",
            command=self.quitter
        ).pack(side=tk.RIGHT, padx=5)

        # Barre de statut
        self.status = ttk.Label(main, text="Prêt.", relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    # ------------------------------------------------------------------
    #  Actions
    # ------------------------------------------------------------------
    def lancer_recherche(self):
        terme = self.entry_recherche.get().strip()
        if not terme:
            messagebox.showinfo("Recherche", "Veuillez saisir un terme.")
            return

        # Vider la liste
        for item in self.tree.get_children():
            self.tree.delete(item)

        resultats = self.db.rechercher(terme)
        for row in resultats:
            self.tree.insert(
                "", tk.END, iid=str(row['id']),
                values=(row['code_interne'], row['ean'] or '',
                        row['description'] or '')
            )

        self.status.config(text=f"{len(resultats)} produit(s) trouvé(s).")
        self._reinitialiser_details()

    def on_selection_produit(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        produit_id = int(sel[0])
        produit = self.db.get_produit(produit_id)
        if not produit:
            return
        self.produit_selectionne = produit
        self._afficher_details(produit)
        self.btn_supprimer.config(state='normal')

    def _reinitialiser_details(self):
        for lbl in self.labels_info.values():
            lbl.config(text="—")
        for item in self.tree_releves.get_children():
            self.tree_releves.delete(item)
        for item in self.tree_conflits.get_children():
            self.tree_conflits.delete(item)
        self.btn_supprimer.config(state='disabled')
        self.produit_selectionne = None

    def _afficher_details(self, produit):
        # Infos
        for cle, lbl in self.labels_info.items():
            valeur = produit[cle] if cle in produit.keys() else ''
            lbl.config(text=str(valeur) if valeur else '—')

        # Relevés de prix
        for item in self.tree_releves.get_children():
            self.tree_releves.delete(item)
        releves = self.db.get_releves_prix(produit['id'])
        for r in releves:
            self.tree_releves.insert("", tk.END, values=(
                r['date_releve'], r['magasin_nom'] or '—',
                r['prix'] or '—', r['prix_old'] or '—',
                r['prix_unit'] or '—'
            ))

        # Conflits EAN
        for item in self.tree_conflits.get_children():
            self.tree_conflits.delete(item)
        conflits = self.db.get_conflits_ean(produit['code_interne'])
        for c in conflits:
            # Déterminer l'"autre" code interne
            autre = c['code_interne_2'] if c['code_interne_1'] == produit['code_interne'] \
                    else c['code_interne_1']
            self.tree_conflits.insert("", tk.END, values=(
                c['ean'], autre, c['date_detection'], c['statut']
            ))

        self.status.config(
            text=(f"Produit sélectionné : {produit['code_interne']} — "
                  f"{len(releves)} relevé(s), {len(conflits)} conflit(s) EAN")
        )

    def supprimer_produit_selectionne(self):
        if not self.produit_selectionne:
            return

        produit = self.produit_selectionne
        releves = self.db.get_releves_prix(produit['id'])
        conflits = self.db.get_conflits_ean(produit['code_interne'])

        # Résumé pour confirmation
        resume = (
            f"Vous êtes sur le point de supprimer définitivement :\n\n"
            f"  • Code interne : {produit['code_interne']}\n"
            f"  • Description  : {produit['description']}\n"
            f"  • EAN          : {produit['ean'] or '—'}\n\n"
            f"Seront également supprimés :\n"
            f"  • {len(releves)} relevé(s) de prix\n"
            f"  • {len(conflits)} conflit(s) EAN lié(s)\n\n"
            f"⚠️ Cette action est IRRÉVERSIBLE.\n\n"
            f"Confirmer la suppression ?"
        )

        if not messagebox.askyesno("Confirmation de suppression", resume,
                                   icon='warning'):
            return

        # Double confirmation
        saisie = self._demander_double_confirmation(produit['code_interne'])
        if saisie is None:
            return
        if saisie.strip() != produit['code_interne']:
            messagebox.showerror("Annulé",
                                 "Le code interne saisi ne correspond pas. "
                                 "Suppression annulée.")
            return

        # Suppression
        try:
            stats = self.db.supprimer_produit(produit['id'])
        except Exception as e:
            messagebox.showerror("Erreur", f"Échec de la suppression :\n{e}")
            return

        messagebox.showinfo(
            "Suppression effectuée",
            f"Le produit {produit['code_interne']} a été supprimé.\n\n"
            f"Détail :\n"
            f"  • Relevés de prix supprimés : {stats['releves']}\n"
            f"  • Conflits EAN supprimés : {stats['conflits']}\n"
            f"  • Produit supprimé : {stats['produit']}"
        )

        self._reinitialiser_details()
        self.lancer_recherche()

    def _demander_double_confirmation(self, code_interne):
        """Boîte de dialogue demandant de retaper le code interne."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Double confirmation")
        dlg.geometry("420x180")
        dlg.transient(self.root)
        dlg.grab_set()

        resultat = {'valeur': None}

        ttk.Label(
            dlg,
            text=(f"Pour confirmer, retapez le code interne :\n\n"
                  f"    {code_interne}"),
            justify=tk.CENTER
        ).pack(pady=15)

        entry = ttk.Entry(dlg, width=30)
        entry.pack(pady=5)
        entry.focus_set()

        def valider():
            resultat['valeur'] = entry.get()
            dlg.destroy()

        def annuler():
            resultat['valeur'] = None
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Confirmer", command=valider).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Annuler", command=annuler).pack(side=tk.LEFT, padx=5)

        entry.bind("<Return>", lambda e: valider())
        dlg.wait_window()
        return resultat['valeur']

    def quitter(self):
        if messagebox.askokcancel("Quitter", "Fermer le programme de suppression ?"):
            self.db.fermer()
            self.root.destroy()


# =====================================================================
#  POINT D'ENTRÉE
# =====================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Suppression d'un produit de la base Eau Vive"
    )
    parser.add_argument("--db", default=DB_PATH_DEFAUT,
                        help="Chemin de la base SQLite")
    args = parser.parse_args()

    root = tk.Tk()
    app = FenetreSuppression(root, db_path=args.db)
    root.mainloop()


if __name__ == "__main__":
    main()