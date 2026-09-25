import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import json
import threading


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "extract-P4"


def extraire_fiche(texte: str) -> dict:
    """Appelle Ollama et retourne le JSON parsé."""
    r = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": texte,
            "stream": False,
            "format": "json",
        },
        timeout=180,
    )
    r.raise_for_status()
    return json.loads(r.json()["response"])


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Extracteur de fiches produit")
        self.geometry("1100x700")

        self.historique = []

        self._build_ui()

    def _build_ui(self):
        # --- Cadre gauche : saisie ---
        frame_gauche = ttk.LabelFrame(self, text="Description produit")
        frame_gauche.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.txt_entree = scrolledtext.ScrolledText(frame_gauche, wrap=tk.WORD, height=25)
        self.txt_entree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        frame_boutons = ttk.Frame(frame_gauche)
        frame_boutons.pack(fill=tk.X, padx=4, pady=4)

        self.btn_analyser = ttk.Button(
            frame_boutons, text="Analyser", command=self.lancer_analyse
        )
        self.btn_analyser.pack(side=tk.LEFT)

        ttk.Button(
            frame_boutons, text="Effacer", command=lambda: self.txt_entree.delete("1.0", tk.END)
        ).pack(side=tk.LEFT, padx=6)

        ttk.Button(
            frame_boutons, text="Copier le JSON", command=self.copier_json
        ).pack(side=tk.LEFT, padx=6)

        self.lbl_statut = ttk.Label(frame_boutons, text="Prêt")
        self.lbl_statut.pack(side=tk.RIGHT)

        # --- Cadre droit : résultat ---
        frame_droite = ttk.LabelFrame(self, text="Résultat JSON")
        frame_droite.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.txt_sortie = scrolledtext.ScrolledText(
            frame_droite, wrap=tk.WORD, height=25, state=tk.DISABLED
        )
        self.txt_sortie.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # --- Historique en bas ---
        frame_hist = ttk.LabelFrame(self, text="Historique (session)")
        frame_hist.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=4)

        self.liste_hist = tk.Listbox(frame_hist, height=5)
        self.liste_hist.pack(fill=tk.X, padx=4, pady=4)
        self.liste_hist.bind("<<ListboxSelect>>", self.charger_historique)

    def lancer_analyse(self):
        texte = self.txt_entree.get("1.0", tk.END).strip()
        if not texte:
            messagebox.showwarning("Champ vide", "Colle d'abord une description.")
            return

        self.lbl_statut.config(text="Analyse en cours…")
        self.btn_analyser.config(state=tk.DISABLED)

        # Thread pour ne pas figer l'interface
        threading.Thread(target=self._analyser_en_thread, args=(texte,), daemon=True).start()

    def _analyser_en_thread(self, texte):
        try:
            resultat = extraire_fiche(texte)
            self.after(0, lambda: self._afficher_resultat(texte, resultat, None))
        except Exception as e:
            self.after(0, lambda: self._afficher_resultat(texte, None, e))

    def _afficher_resultat(self, texte, resultat, erreur):
        self.btn_analyser.config(state=tk.NORMAL)

        if erreur:
            self.lbl_statut.config(text="Erreur")
            messagebox.showerror("Erreur", str(erreur))
            return

        self.txt_sortie.config(state=tk.NORMAL)
        self.txt_sortie.delete("1.0", tk.END)
        self.txt_sortie.insert(
            tk.END, json.dumps(resultat, ensure_ascii=False, indent=2)
        )
        self.txt_sortie.config(state=tk.DISABLED)

        # Ajout à l'historique
        nom = resultat.get("nom_produit", "?")
        marque = resultat.get("marque", "?")
        entree = f"{nom} — {marque}"
        self.historique.append({"label": entree, "texte": texte, "resultat": resultat})
        self.liste_hist.insert(tk.END, entree)

        self.lbl_statut.config(text="OK")

    def copier_json(self):
        contenu = self.txt_sortie.get("1.0", tk.END).strip()
        if contenu:
            self.clipboard_clear()
            self.clipboard_append(contenu)
            self.lbl_statut.config(text="JSON copié")

    def charger_historique(self, event):
        sel = self.liste_hist.curselection()
        if not sel:
            return
        item = self.historique[sel[0]]
        self.txt_entree.delete("1.0", tk.END)
        self.txt_entree.insert(tk.END, item["texte"])
        self.txt_sortie.config(state=tk.NORMAL)
        self.txt_sortie.delete("1.0", tk.END)
        self.txt_sortie.insert(
            tk.END, json.dumps(item["resultat"], ensure_ascii=False, indent=2)
        )
        self.txt_sortie.config(state=tk.DISABLED)


if __name__ == "__main__":
    app = App()
    app.mainloop()