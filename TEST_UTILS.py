from utils.db_utils import get_marques_uniques, get_marques_with_count

# Récupérer simplement les marques
marques = get_marques_uniques("EauVive_prix.db")
print(marques)

# Récupérer les marques avec le nombre de produits
marques_stats = get_marques_with_count("EauVive_prix.db")
for marque, nb in marques_stats:
    print(f"{marque} : {nb} produits")