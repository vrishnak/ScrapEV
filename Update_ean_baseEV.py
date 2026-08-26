import csv
import sqlite3


CSV_FILE = "IMPORT2.csv"
DB_FILE = "EauVive_prix.db"


def mettre_a_jour_ean():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as fichier:
        reader = csv.DictReader(fichier, delimiter=";")

        nb_lus = 0
        nb_maj = 0

        for ligne in reader:
            nb_lus += 1

            code_interne = str(ligne["code_interne"]).strip()
            ean = str(ligne["ean"]).strip()

            # EAN vide : on ignore
            if not ean:
                continue

            # Vérifie si l'EAN existe déjà dans PRODUITS
            cursor.execute(
                """
                SELECT 1
                FROM PRODUITS
                WHERE ean = ?
                LIMIT 1
                """,
                (ean,)
            )

            if cursor.fetchone() is not None:
                # L'EAN existe déjà, aucune modification nécessaire
                continue

            # L'EAN n'existe pas : mise à jour uniquement
            # du produit ayant le même code_interne
            cursor.execute(
                """
                UPDATE PRODUITS
                SET ean = ?
                WHERE code_interne = ?
                """,
                (ean, code_interne)
            )

            if cursor.rowcount > 0:
                nb_maj += cursor.rowcount

    conn.commit()
    conn.close()

    print(f"{nb_lus} lignes CSV lues.")
    print(f"{nb_maj} produit(s) mis à jour.")


if __name__ == "__main__":
    mettre_a_jour_ean()