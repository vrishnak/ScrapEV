. Installer Ollama
Rends-toi sur ollama.com et télécharge l'installateur pour ton système (Windows, macOS, Linux). L'installation est standard.

2. Récupérer le modèle Gemma 3 1B de base
Ouvre un terminal et exécute cette commande pour télécharger le modèle de base (la version optimisée pour les petits appareils) :
bash

ollama run gemma3:1b

Cette commande télécharge et lance le modèle. Tu peux quitter avec /bye .


3. Charger le modèle fine-tuné pour l'extraction produit
Le modèle de Dinesh-Kumar n'est pas directement sur le registre Ollama, mais tu peux l'exécuter via llama.cpp (le moteur derrière Ollama) ou en le convertissant. Cependant, pour un premier test, tu peux déjà voir si le modèle de base Gemma 3 1B, avec un bon prompt, arrive à faire le travail.

4. Tester avec un prompt
Crée un fichier Modelfile pour personnaliser ton modèle avec un prompt système qui décrit la tâche. Par exemple :
dockerfile

FROM gemma3:1b

PARAMETER temperature 0.1
PARAMETER top_k 64
PARAMETER top_p 0.95

SYSTEM """
Tu es un extracteur d'informations produit. À partir d'une description désordonnée, tu dois retourner UNIQUEMENT un JSON valide avec cette structure exacte :
{
  "brand": "nom_de_la_marque",
  "product": "nom_du_produit_en_2_a_3_mots",
  "keywords": ["mot1", "mot2", "mot3", "mot4", "mot5"],
  "quantity": "nombre unite"
}

Règles :
- Les keywords ne doivent PAS contenir d'information de quantité.
- La quantité doit être normalisée (ex: "800 Gram", "400 Milliliter").
- Les unités autorisées : Gram, Kilogram, Milliliter, Liter, Sachet, Unit, etc.
- Retourne UNIQUEMENT le JSON, sans texte avant ou après.
"""

Puis crée ton modèle personnalisé :
bash

ollama create extracteur-produit -f Modelfile

Et teste-le :
bash

ollama run extracteur-produit "Lait de croissance Optima 3 dès 10 mois Babybio 800g"

⚠️ Limitations du modèle de base

Le Gemma 3 1B non fine-tuné peut ne pas être fiable pour cette tâche précise. Le fine-tuning de Dinesh-Kumar a été nécessaire justement parce que le modèle de base avait du mal à extraire correctement les mots-clés et à retirer les quantités .

Si les résultats ne sont pas bons, tu auras deux options :

    Convertir le modèle fine-tuné en GGUF pour l'utiliser avec Ollama. Cela demande un peu plus de travail (télécharger le modèle depuis Hugging Face, le convertir avec llama.cpp).

    Fine-tuner toi-même Gemma 3 1B sur tes propres données annotées. C'est plus long mais te donnera les meilleurs résultats sur ton catalogue spécifique (Babybio, Good Goût, etc.). Des tutoriels existent avec Unsloth ou Hugging Face + TRL .

💡 Pour un test rapide sans installation

Si tu veux juste voir ce que Gemma 3 1B peut faire avec un bon prompt, tu peux utiliser le playground de Google AI Studio (gratuit, en ligne) avant de te lancer dans l'installation locale. Mais pour traiter 10 000 produits, l'installation locale est indispensable.

Veux-tu que je te détaille la procédure pour convertir le modèle fine-tuné de Dinesh-Kumar en GGUF pour Ollama ?
