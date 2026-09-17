import json
import numpy as np
from sentence_transformers import SentenceTransformer


# ============================================================
# CONFIGURATION
# ============================================================

FICHIER = "produits_vectorises.json"
MODELE = "paraphrase-multilingual-MiniLM-L12-v2"

# Produit que l'on veut surveiller particulièrement
REF_TEST = "93203"

# Requêtes de test
REQUETES = [
    "lessive",
    "lessive liquide",
    "lessive pour le linge",
    "produit pour laver le linge",
    "lavage du linge",
    "assouplissant",
    "percarbonate de soude",
    "bicarbonate de soude",
    "liquide vaisselle",
    "shampoing",
]


# ============================================================
# AFFICHAGE
# ============================================================

def titre(texte):
    print()
    print("=" * 75)
    print(texte)
    print("=" * 75)


# ============================================================
# 1. CHARGEMENT DU JSON
# ============================================================

titre("1. CHARGEMENT DU FICHIER")

try:
    with open(FICHIER, "r", encoding="utf-8") as f:
        produits = json.load(f)

    print(f"Fichier chargé : {FICHIER}")
    print(f"Nombre de produits : {len(produits)}")

except Exception as e:
    print("ERREUR lors du chargement :")
    print(e)
    raise SystemExit


# ============================================================
# 2. VERIFICATION DE LA STRUCTURE
# ============================================================

titre("2. VERIFICATION DE LA STRUCTURE")

champs_obligatoires = [
    "ref_id",
    "description",
    "texte_embedding",
    "embedding",
]

problemes_structure = 0

for i, produit in enumerate(produits):

    if not isinstance(produit, dict):
        print(f"Produit {i}: ce n'est pas un dictionnaire")
        problemes_structure += 1
        continue

    for champ in champs_obligatoires:
        if champ not in produit:
            print(
                f"Produit {i} / ref_id={produit.get('ref_id')} "
                f": champ manquant -> {champ}"
            )
            problemes_structure += 1

print()
print(f"Nombre de problèmes de structure : {problemes_structure}")


# ============================================================
# 3. VERIFICATION DES EMBEDDINGS
# ============================================================

titre("3. VERIFICATION DES EMBEDDINGS")

dimensions = []
embeddings_valides = []
produits_valides = []

nb_manquants = 0
nb_vides = 0
nb_invalides = 0

for produit in produits:

    embedding = produit.get("embedding")

    if embedding is None:
        nb_manquants += 1
        continue

    if not isinstance(embedding, list) or len(embedding) == 0:
        nb_vides += 1
        continue

    try:
        vecteur = np.asarray(embedding, dtype=np.float32)

        if not np.all(np.isfinite(vecteur)):
            nb_invalides += 1
            continue

        dimensions.append(len(vecteur))
        embeddings_valides.append(vecteur)
        produits_valides.append(produit)

    except Exception:
        nb_invalides += 1


print(f"Embeddings valides : {len(embeddings_valides)}")
print(f"Embeddings manquants : {nb_manquants}")
print(f"Embeddings vides : {nb_vides}")
print(f"Embeddings invalides : {nb_invalides}")

if dimensions:
    dimensions_uniques = sorted(set(dimensions))

    print(f"Dimensions trouvées : {dimensions_uniques}")

    if len(dimensions_uniques) == 1:
        print("OK : tous les embeddings ont la même dimension.")
    else:
        print("ATTENTION : les dimensions sont différentes !")


# ============================================================
# 4. NORMALE DES VECTEURS
# ============================================================

titre("4. NORME DES EMBEDDINGS")

normes = []

for vecteur in embeddings_valides:
    norme = np.linalg.norm(vecteur)
    normes.append(norme)

normes = np.asarray(normes)

print(f"Norme minimale : {normes.min():.6f}")
print(f"Norme maximale : {normes.max():.6f}")
print(f"Norme moyenne  : {normes.mean():.6f}")

print()

if np.allclose(normes, 1.0, atol=0.01):
    print("Les vecteurs semblent déjà normalisés.")
else:
    print("Les vecteurs ne sont PAS normalisés à 1.")
    print("Ce n'est pas forcément un problème :")
    print("on les normalisera avant le calcul cosinus.")


# ============================================================
# 5. CONSTRUCTION DE LA MATRICE
# ============================================================

titre("5. CONSTRUCTION DE LA MATRICE")

embeddings_matrix = np.vstack(embeddings_valides)

print("Shape de la matrice :")
print(embeddings_matrix.shape)

print()
print("Exemple attendu :")
print("(nombre_de_produits, 384)")


# ============================================================
# 6. NORMALISATION
# ============================================================

normes = np.linalg.norm(
    embeddings_matrix,
    axis=1,
    keepdims=True
)

embeddings_normalises = (
    embeddings_matrix /
    np.clip(normes, 1e-12, None)
)

print()
print("Matrice normalisée.")


# ============================================================
# 7. CHARGEMENT DU MODELE
# ============================================================

titre("6. CHARGEMENT DU MODELE")

print(f"Modèle : {MODELE}")

model = SentenceTransformer(MODELE)

print("Modèle chargé.")


# ============================================================
# 8. TEST SIMPLE DU MODELE
# ============================================================

titre("7. TEST DU MODELE")

requete_test = "lessive"

vecteur_requete = model.encode(
    requete_test,
    normalize_embeddings=True
)

print(f"Requête : {requete_test}")
print(f"Dimension : {len(vecteur_requete)}")
print(f"Norme : {np.linalg.norm(vecteur_requete):.6f}")

if len(vecteur_requete) == embeddings_matrix.shape[1]:
    print("OK : dimension requête = dimension produits.")
else:
    print("ERREUR : dimensions différentes !")


# ============================================================
# 9. TEST DIRECT DU PRODUIT 93203
# ============================================================

titre("8. TEST DU PRODUIT 93203")

produit_test = None
index_test = None

for i, produit in enumerate(produits_valides):

    if str(produit.get("ref_id")) == REF_TEST:
        produit_test = produit
        index_test = i
        break


if produit_test is None:

    print(f"Produit {REF_TEST} introuvable.")

else:

    print("Produit trouvé :")
    print(f"ref_id      : {produit_test.get('ref_id')}")
    print(f"description : {produit_test.get('description')}")
    print(f"texte       : {produit_test.get('texte_embedding')}")

    vecteur_produit = embeddings_normalises[index_test]

    score = np.dot(
        vecteur_requete,
        vecteur_produit
    )

    print()
    print(f"Similarité avec 'lessive' : {score:.7f}")


# ============================================================
# 10. COHERENCE VECTEUR STOCKE / VECTEUR RECALCULE
# ============================================================

titre("9. COHERENCE DES EMBEDDINGS STOCKES")

# On teste quelques produits plutôt que tout le catalogue
nb_tests = min(10, len(produits_valides))

scores_coherence = []

for i in range(nb_tests):

    produit = produits_valides[i]

    texte = produit.get("texte_embedding")

    if not texte:
        continue

    vecteur_frais = model.encode(
        texte,
        normalize_embeddings=True
    )

    vecteur_stocke = embeddings_normalises[i]

    score = np.dot(
        vecteur_frais,
        vecteur_stocke
    )

    scores_coherence.append(score)

    print(
        f"ref_id={produit.get('ref_id')} "
        f"| cohérence = {score:.7f}"
    )


if scores_coherence:

    print()
    print(
        f"Cohérence moyenne : "
        f"{np.mean(scores_coherence):.7f}"
    )

    print(
        f"Cohérence minimale : "
        f"{np.min(scores_coherence):.7f}"
    )


# ============================================================
# 11. RECHERCHE SEMANTIQUE
# ============================================================

def rechercher(requete, k=10):

    # Embedding de la requête
    q = model.encode(
        requete,
        normalize_embeddings=True
    )

    # Similarité cosinus
    scores = embeddings_normalises @ q

    # TRI DECROISSANT
    indices = np.argsort(scores)[::-1][:k]

    resultats = []

    for rang, index in enumerate(indices, start=1):

        produit = produits_valides[index]

        resultats.append({
            "rang": rang,
            "score": float(scores[index]),
            "ref_id": produit.get("ref_id"),
            "description": produit.get("description"),
        })

    return resultats


# ============================================================
# 12. TEST DE "LESSIVE"
# ============================================================

titre("10. RECHERCHE : LESSIVE")

resultats = rechercher("lessive", 20)

for r in resultats:

    print(
        f"{r['rang']:2d}. "
        f"{r['score']:.7f} | "
        f"{r['ref_id']} | "
        f"{r['description']}"
    )


# ============================================================
# 13. POSITION DU PRODUIT 93203
# ============================================================

titre("11. POSITION DU PRODUIT 93203")

position_93203 = None
score_93203 = None

for r in resultats:

    if str(r["ref_id"]) == REF_TEST:
        position_93203 = r["rang"]
        score_93203 = r["score"]
        break


if position_93203:

    print(f"Produit 93203 trouvé en position : {position_93203}")
    print(f"Score : {score_93203:.7f}")

    if position_93203 <= 3:
        print("Le produit est très bien classé.")
    elif position_93203 <= 10:
        print("Le produit est dans le TOP 10.")
    else:
        print("ATTENTION : le produit est relativement mal classé.")

else:

    print("Le produit 93203 n'est pas dans les résultats.")


# ============================================================
# 14. TEST DE PLUSIEURS REQUETES
# ============================================================

titre("12. TEST DE PLUSIEURS REQUETES")

for requete in REQUETES:

    print()
    print("-" * 75)
    print(f"REQUETE : {requete}")
    print("-" * 75)

    resultats = rechercher(requete, 5)

    for r in resultats:

        print(
            f"{r['rang']}. "
            f"{r['score']:.4f} | "
            f"{r['ref_id']} | "
            f"{r['description']}"
        )


# ============================================================
# 15. TEST DES SCORES DE QUELQUES PRODUITS
# ============================================================

titre("13. TEST DIRECT SUR QUELQUES PRODUITS")

produits_a_tester = [
    "93203",  # Lessive
]

# On ajoute automatiquement les premiers produits du catalogue
for produit in produits_valides[:5]:

    ref = str(produit.get("ref_id"))

    if ref not in produits_a_tester:
        produits_a_tester.append(ref)


for ref in produits_a_tester:

    for i, produit in enumerate(produits_valides):

        if str(produit.get("ref_id")) == ref:

            score = np.dot(
                vecteur_requete,
                embeddings_normalises[i]
            )

            print(
                f"ref_id={ref} | "
                f"score={score:.7f} | "
                f"{produit.get('description')}"
            )

            break


# ============================================================
# 16. RESUME FINAL
# ============================================================

titre("14. RESUME DU DIAGNOSTIC")

print(f"Nombre total de produits       : {len(produits)}")
print(f"Embeddings valides              : {len(embeddings_valides)}")

if dimensions:
    print(f"Dimension des embeddings        : {dimensions_uniques}")

print(
    f"Dimension embedding requête    : "
    f"{len(vecteur_requete)}"
)

print(
    f"Norme moyenne embeddings       : "
    f"{normes.mean():.6f}"
)

if produit_test is not None:

    print(
        f"Score 'lessive' / produit 93203 : "
        f"{score_93203:.7f}"
    )

    print(
        f"Position produit 93203          : "
        f"{position_93203}"
    )

print()
print("DIAGNOSTIC TERMINE")


titre("TEST SEMANTIQUE DIRECT")

tests = [
    "lessive",
    "Lessive",
    "lessive liquide",
    "Lessive douceur",
    "Lessive pour le linge",
    "Produit lessive",
    "Produit : Lessive douceur sans parfum Safe 1L\nFormat : 1L",
    "Buvard cannelle verte Buvard D'Encens",
    "Sac vrac petit bouchon Fillgood",
    "Eponge vegetale grattante",
]

q = model.encode(
    "lessive",
    normalize_embeddings=True
)

for texte in tests:

    v = model.encode(
        texte,
        normalize_embeddings=True
    )

    score = np.dot(q, v)

    print(f"{score:.7f} | {texte}")

    titre("COMPARAISON DES TEXTES PRODUITS")

    textes = {
        "A - texte actuel":
            "Produit : Lessive douceur sans parfum Safe 1L\nFormat : 1L",

        "B - description":
            "Lessive douceur sans parfum Safe 1L",

        "C - texte enrichi":
            "Lessive pour laver le linge, produit de lavage du linge, "
            "lessive liquide, sans parfum, 1L",
    }

    q = model.encode(
        "lessive",
        normalize_embeddings=True
    )

    for nom, texte in textes.items():
        v = model.encode(
            texte,
            normalize_embeddings=True
        )

        score = np.dot(q, v)

        print()
        print(nom)
        print("Texte :", texte)
        print(f"Score : {score:.7f}")
