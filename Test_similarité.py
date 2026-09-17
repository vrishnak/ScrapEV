import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FILE = "produits_vectorises.json"

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Nombre de résultats à afficher
TOP_K = 10


# ============================================================
# CHARGEMENT DU MODELE
# ============================================================

print("Chargement du modèle...")

model = SentenceTransformer(
    EMBEDDING_MODEL
)

print("Modèle chargé.")


# ============================================================
# CHARGEMENT DES PRODUITS
# ============================================================

input_path = Path(INPUT_FILE)

if not input_path.exists():

    raise FileNotFoundError(
        f"Fichier introuvable : {INPUT_FILE}"
    )


with open(
    input_path,
    "r",
    encoding="utf-8"
) as fichier:

    produits = json.load(fichier)


if not isinstance(produits, list):

    raise ValueError(
        "Le fichier JSON doit contenir une liste."
    )


print(
    f"{len(produits)} produits chargés."
)


# ============================================================
# VERIFICATION DES EMBEDDINGS
# ============================================================

produits_valides = []

for produit in produits:

    embedding = produit.get("embedding")

    if not embedding:
        continue

    produits_valides.append(
        produit
    )


print(
    f"{len(produits_valides)} produits possèdent "
    "un embedding."
)


if not produits_valides:

    raise ValueError(
        "Aucun embedding trouvé dans le fichier."
    )


# ============================================================
# CONVERSION DES EMBEDDINGS
# ============================================================

embeddings = np.array(
    [
        produit["embedding"]
        for produit in produits_valides
    ],
    dtype=np.float32
)


# ============================================================
# FONCTION DE SIMILARITE
# ============================================================

def rechercher_produits(
    requete,
    top_k=10
):
    """
    Recherche les produits les plus similaires
    à une requête utilisateur.
    """

    # --------------------------------------------------------
    # VECTORISATION DE LA REQUETE
    # --------------------------------------------------------

    vecteur_requete = model.encode(
        requete,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    # --------------------------------------------------------
    # SIMILARITE COSINUS
    # --------------------------------------------------------

    # Les embeddings ayant été normalisés,
    # le produit scalaire correspond à la similarité cosinus.

    scores = np.dot(
        embeddings,
        vecteur_requete
    )

    # --------------------------------------------------------
    # TRI DES RESULTATS
    # --------------------------------------------------------

    indices = np.argsort(
        scores
    )[::-1]

    indices = indices[:top_k]

    # --------------------------------------------------------
    # AFFICHAGE
    # --------------------------------------------------------

    print()
    print("=" * 80)

    print(
        f"RECHERCHE : {requete}"
    )

    print("=" * 80)

    for position, index in enumerate(
        indices,
        start=1
    ):

        produit = produits_valides[index]

        score = scores[index]

        print()
        print(
            f"{position}. "
            f"{produit.get('description', 'Sans description')}"
        )

        print(
            f"   ref_id : {produit.get('ref_id')}"
        )

        print(
            f"   Score : {score:.4f}"
        )

        print(
            f"   Prix : {produit.get('prix', '')}"
        )

        print(
            f"   Lien : {produit.get('lien', '')}"
        )


# ============================================================
# MODE INTERACTIF
# ============================================================

print()
print("=" * 80)
print("TEST DE RECHERCHE SEMANTIQUE")
print("=" * 80)

print()
print(
    "Entre une recherche utilisateur."
)

print(
    "Tape 'quit' pour quitter."
)

while True:

    print()

    requete = input(
        "Recherche : "
    ).strip()

    if requete.lower() in (
        "quit",
        "exit",
        "q"
    ):

        break

    if not requete:

        continue

    rechercher_produits(
        requete,
        TOP_K
    )


print()
print("Fin du test.")
