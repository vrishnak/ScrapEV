import json
import os
import time
from pathlib import Path

from openai import OpenAI


# ============================================================
# CONFIGURATION
# ============================================================

# Fichier JSON contenant les produits sources.
INPUT_FILE = "produits.json"

# Fichier JSON de sortie contenant les produits vectorisés.
OUTPUT_FILE = "produits_vectorises.json"

# Modèle utilisé pour créer les embeddings.
EMBEDDING_MODEL = "text-embedding-3-small"

# Nombre maximum de tentatives en cas d'erreur temporaire.
MAX_RETRIES = 3

# Temps d'attente initial entre deux tentatives.
RETRY_DELAY = 2


# ============================================================
# VERIFICATION DE LA CLE API
# ============================================================

api_key = os.environ.get("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError(
        "La variable d'environnement OPENAI_API_KEY "
        "n'est pas définie."
    )

# On affiche uniquement une partie de la clé pour vérifier
# que Python utilise bien une clé, sans révéler la clé complète.
print(
    f"Clé API détectée : "
    f"{api_key[:10]}...{api_key[-4:]}"
)


# ============================================================
# CLIENT OPENAI
# ============================================================
print("Clé utilisée par Python :", api_key[:10] + "..." + api_key[-4:])
client = OpenAI(
    api_key=api_key
)


# ============================================================
# CHARGEMENT DU FICHIER SOURCE
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


# Vérification : on attend une liste de produits.
if not isinstance(produits, list):
    raise ValueError(
        "Le fichier JSON doit contenir une liste de produits."
    )


print()
print(f"{len(produits)} produits trouvés.")


# ============================================================
# CHARGEMENT DU FICHIER DE SORTIE EXISTANT
# ============================================================

output_path = Path(OUTPUT_FILE)

if output_path.exists():

    print(
        f"Fichier existant détecté : {OUTPUT_FILE}"
    )

    with open(
        output_path,
        "r",
        encoding="utf-8"
    ) as fichier:

        produits_vectorises = json.load(fichier)

    # Vérification de sécurité.
    if not isinstance(produits_vectorises, list):
        raise ValueError(
            f"{OUTPUT_FILE} doit contenir une liste."
        )

else:

    print(
        "Aucun fichier de sortie existant. "
        "Création d'un nouveau fichier."
    )

    produits_vectorises = []


# ============================================================
# INDEX DES PRODUITS DEJA TRAITES
# ============================================================

# On construit un dictionnaire permettant de retrouver
# rapidement un produit déjà vectorisé.
#
# On utilise ref_id comme identifiant principal.
produits_existants = {}

for produit in produits_vectorises:

    ref_id = produit.get("ref_id")

    if ref_id is not None:
        produits_existants[str(ref_id)] = produit


print(
    f"{len(produits_existants)} produits déjà vectorisés."
)


# ============================================================
# CONSTRUCTION DU TEXTE SEMANTIQUE
# ============================================================

def construire_texte_embedding(produit):
    """
    Transforme les informations d'un produit en texte.

    Ce texte est ensuite envoyé au modèle d'embedding.

    IMPORTANT :
    On ne vectorise pas directement le JSON brut.

    On sélectionne les informations qui ont une valeur
    sémantique pour la recherche de produits similaires.
    """

    lignes = []

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    description = produit.get("description")

    if description:
        lignes.append(
            f"Produit : {description}"
        )

    # --------------------------------------------------------
    # MARQUE
    # --------------------------------------------------------

    marque = produit.get("marque")

    if marque:
        lignes.append(
            f"Marque : {marque}"
        )

    # --------------------------------------------------------
    # CATEGORIE
    # --------------------------------------------------------

    categorie = produit.get("categorie")

    if categorie:
        lignes.append(
            f"Catégorie : {categorie}"
        )

    # --------------------------------------------------------
    # SOUS-CATEGORIE
    # --------------------------------------------------------

    sous_categorie = produit.get("sous_categorie")

    if sous_categorie:
        lignes.append(
            f"Sous-catégorie : {sous_categorie}"
        )

    # --------------------------------------------------------
    # TYPE DE PRODUIT
    # --------------------------------------------------------

    type_produit = produit.get("type_produit")

    if type_produit:
        lignes.append(
            f"Type de produit : {type_produit}"
        )

    # --------------------------------------------------------
    # CARACTERISTIQUES
    # --------------------------------------------------------

    caracteristiques = produit.get(
        "caracteristiques"
    )

    if isinstance(caracteristiques, dict):

        lignes.append(
            "Caractéristiques :"
        )

        for nom, valeur in caracteristiques.items():

            # Si la valeur est une liste,
            # on la transforme en texte.
            if isinstance(valeur, list):

                valeur = ", ".join(
                    str(element)
                    for element in valeur
                )

            # Si la valeur est un dictionnaire,
            # on le transforme également en JSON lisible.
            elif isinstance(valeur, dict):

                valeur = json.dumps(
                    valeur,
                    ensure_ascii=False
                )

            lignes.append(
                f"- {nom} : {valeur}"
            )

    # --------------------------------------------------------
    # TAGS
    # --------------------------------------------------------

    tags = produit.get("tags", [])

    if tags:

        if isinstance(tags, list):

            tags_texte = ", ".join(
                str(tag)
                for tag in tags
            )

        else:

            tags_texte = str(tags)

        lignes.append(
            f"Tags : {tags_texte}"
        )

    # --------------------------------------------------------
    # ALLERGENES
    # --------------------------------------------------------

    allergenes = produit.get(
        "allergenes",
        []
    )

    if allergenes:

        if isinstance(allergenes, list):

            allergenes_texte = ", ".join(
                str(allergene)
                for allergene in allergenes
            )

        else:

            allergenes_texte = str(allergenes)

        lignes.append(
            f"Allergènes : {allergenes_texte}"
        )

    # --------------------------------------------------------
    # VOLUME / FORMAT
    # --------------------------------------------------------

    volume = produit.get("volume")

    if volume:
        lignes.append(
            f"Format : {volume}"
        )

    # --------------------------------------------------------
    # RESULTAT
    # --------------------------------------------------------

    return "\n".join(lignes)


# ============================================================
# GENERATION D'UN EMBEDDING
# ============================================================

def generer_embedding(texte):
    """
    Génère le vecteur correspondant au texte.

    En cas d'erreur temporaire, le programme réessaie
    plusieurs fois avant d'abandonner le produit.
    """

    for tentative in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texte
            )

            return response.data[0].embedding

        except Exception as erreur:

            print(
                f"    Erreur API "
                f"(tentative {tentative}/{MAX_RETRIES}) : "
                f"{erreur}"
            )

            # Si ce n'est pas la dernière tentative,
            # on attend avant de recommencer.
            if tentative < MAX_RETRIES:

                delai = (
                    RETRY_DELAY * tentative
                )

                print(
                    f"    Nouvelle tentative "
                    f"dans {delai} secondes..."
                )

                time.sleep(delai)

    # Toutes les tentatives ont échoué.
    return None


# ============================================================
# SAUVEGARDE
# ============================================================

def sauvegarder(produits):
    """
    Sauvegarde immédiatement le catalogue.

    Le fichier est réécrit après chaque produit traité.
    C'est volontaire : cela permet de reprendre le traitement
    après une interruption.
    """

    # On écrit d'abord dans un fichier temporaire.
    # Cela évite de risquer de corrompre le fichier principal
    # si le programme est interrompu pendant l'écriture.
    fichier_temporaire = (
        OUTPUT_FILE + ".tmp"
    )

    with open(
        fichier_temporaire,
        "w",
        encoding="utf-8"
    ) as fichier:

        json.dump(
            produits,
            fichier,
            ensure_ascii=False,
            indent=2
        )

    # Remplacement du fichier principal.
    os.replace(
        fichier_temporaire,
        OUTPUT_FILE
    )


# ============================================================
# TRAITEMENT DES PRODUITS
# ============================================================

nombre_total = len(produits)

nombre_deja_faits = 0
nombre_nouveaux = 0
nombre_erreurs = 0


for index, produit in enumerate(
    produits,
    start=1
):

    # --------------------------------------------------------
    # IDENTIFIANT
    # --------------------------------------------------------

    ref_id = produit.get("ref_id")

    if ref_id is None:

        print(
            f"\n[{index}/{nombre_total}] "
            "Produit sans ref_id → ignoré."
        )

        nombre_erreurs += 1
        continue

    ref_id = str(ref_id)

    # --------------------------------------------------------
    # VERIFICATION SI DEJA VECTORISE
    # --------------------------------------------------------

    if ref_id in produits_existants:

        produit_existant = (
            produits_existants[ref_id]
        )

        # On vérifie que le vecteur existe réellement.
        embedding_existant = (
            produit_existant.get("embedding")
        )

        if embedding_existant:

            print(
                f"[{index}/{nombre_total}] "
                f"{produit.get('description', 'Sans nom')} "
                f"→ déjà vectorisé, SKIP"
            )

            nombre_deja_faits += 1
            continue

    # --------------------------------------------------------
    # AFFICHAGE
    # --------------------------------------------------------

    print()
    print(
        f"[{index}/{nombre_total}] "
        f"Vectorisation : "
        f"{produit.get('description', 'Sans nom')}"
    )

    # --------------------------------------------------------
    # CONSTRUCTION DU TEXTE
    # --------------------------------------------------------

    texte_embedding = (
        construire_texte_embedding(produit)
    )

    print(
        "    Texte sémantique construit."
    )

    # --------------------------------------------------------
    # GENERATION DU VECTEUR
    # --------------------------------------------------------

    embedding = generer_embedding(
        texte_embedding
    )

    # --------------------------------------------------------
    # ECHEC
    # --------------------------------------------------------

    if embedding is None:

        print(
            "    ❌ Impossible de vectoriser "
            "ce produit."
        )

        nombre_erreurs += 1

        continue

    # --------------------------------------------------------
    # CREATION DU PRODUIT VECTORISE
    # --------------------------------------------------------

    produit_vectorise = produit.copy()

    # Texte exact envoyé au modèle.
    produit_vectorise[
        "texte_embedding"
    ] = texte_embedding

    # Vecteur numérique.
    produit_vectorise[
        "embedding"
    ] = embedding

    # Modèle utilisé.
    produit_vectorise[
        "embedding_model"
    ] = EMBEDDING_MODEL

    # Version logique du pipeline.
    # Très utile si tu modifies plus tard
    # la manière de construire le texte.
    produit_vectorise[
        "embedding_version"
    ] = 1

    # --------------------------------------------------------
    # MISE A JOUR DU DICTIONNAIRE
    # --------------------------------------------------------

    produits_existants[ref_id] = (
        produit_vectorise
    )

    nombre_nouveaux += 1

    # --------------------------------------------------------
    # RECONSTRUCTION DE LA LISTE
    # --------------------------------------------------------

    produits_vectorises = list(
        produits_existants.values()
    )

    # --------------------------------------------------------
    # SAUVEGARDE IMMEDIATE
    # --------------------------------------------------------

    sauvegarder(
        produits_vectorises
    )

    print(
        f"    ✅ Vecteur généré "
        f"({len(embedding)} dimensions)"
    )

    print(
        f"    💾 Sauvegarde effectuée."
    )


# ============================================================
# RESUME FINAL
# ============================================================

print()
print("=" * 60)
print("VECTORISATION TERMINEE")
print("=" * 60)

print(
    f"Produits dans le fichier source : "
    f"{nombre_total}"
)

print(
    f"Déjà vectorisés : "
    f"{nombre_deja_faits}"
)

print(
    f"Nouveaux vecteurs générés : "
    f"{nombre_nouveaux}"
)

print(
    f"Erreurs : "
    f"{nombre_erreurs}"
)

print()
print(
    f"Fichier de sortie : "
    f"{OUTPUT_FILE}"
)

print(
    f"Modèle : "
    f"{EMBEDDING_MODEL}"
)

