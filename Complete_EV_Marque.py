import sqlite3
import re


def mise_a_jour_marques_validation_ligne():
    """
    Programme qui met à jour PRODUITS['marque'] avec le NOM de la marque
    avec validation ligne par ligne
    """

    # Connexion à la base de données
    conn = sqlite3.connect('EauVive_prix.db')
    cursor = conn.cursor()

    try:
        print("=" * 80)
        print("MISE À JOUR DES MARQUES - VALIDATION LIGNE PAR LIGNE")
        print("=" * 80)

        # 1. Récupérer toutes les marques depuis MARQUES['nom']
        cursor.execute("SELECT id, nom FROM MARQUES ORDER BY nom")
        marques = cursor.fetchall()

        if not marques:
            print("❌ Aucune marque trouvée dans la table MARQUES")
            return

        print(f"📋 {len(marques)} marques chargées depuis MARQUES['nom']")
        print("-" * 80)

        # 2. Récupérer les produits dont PRODUITS['marque'] est NULL
        cursor.execute("""
            SELECT id, description 
            FROM PRODUITS 
            WHERE marque IS NULL AND description IS NOT NULL
        """)
        produits_sans_marque = cursor.fetchall()

        if not produits_sans_marque:
            print("✅ Tous les produits ont déjà une marque !")
            return

        print(f"📦 {len(produits_sans_marque)} produits sans marque à traiter")
        print("=" * 80)

        # 3. Pour chaque produit, chercher une marque dans sa description
        produits_mis_a_jour = 0
        produits_ignores = 0
        produits_non_trouves = 0

        for idx, (produit_id, description) in enumerate(produits_sans_marque, 1):
            print(f"\n📌 Produit {idx}/{len(produits_sans_marque)} - ID: {produit_id}")
            print(f"   Description: {description}")
            print("-" * 80)

            # Chercher toutes les marques présentes dans la description
            description_lower = description.lower()
            marques_trouvees = []

            for marque_id, marque_nom in marques:
                if marque_nom.lower() in description_lower:
                    marques_trouvees.append((marque_id, marque_nom))

            if not marques_trouvees:
                print("   ❌ Aucune marque trouvée dans la description")
                produits_non_trouves += 1
                continue

            # Afficher les marques trouvées
            print(f"   🏷️  Marques trouvées dans la description :")
            for i, (m_id, m_nom) in enumerate(marques_trouvees, 1):
                print(f"      {i}. {m_nom} (ID: {m_id})")

            # Si plusieurs marques, proposer un choix
            if len(marques_trouvees) > 1:
                print(f"\n   ⚠️  Plusieurs marques trouvées !")
                choix = input(f"   Choisissez la marque (1-{len(marques_trouvees)}) ou 0 pour ignorer : ")

                try:
                    choix_int = int(choix)
                    if choix_int == 0:
                        print("   ⏭️  Produit ignoré")
                        produits_ignores += 1
                        continue
                    elif 1 <= choix_int <= len(marques_trouvees):
                        marque_choisie = marques_trouvees[choix_int - 1]
                        nom_marque = marque_choisie[1]  # On prend le NOM, pas l'ID
                    else:
                        print("   ❌ Choix invalide, produit ignoré")
                        produits_ignores += 1
                        continue
                except ValueError:
                    print("   ❌ Choix invalide, produit ignoré")
                    produits_ignores += 1
                    continue
            else:
                # Une seule marque trouvée
                marque_choisie = marques_trouvees[0]
                nom_marque = marque_choisie[1]  # On prend le NOM, pas l'ID

                # Demander confirmation
                print(f"\n   ➜ Marque à appliquer: {nom_marque}")
                reponse = input("   Appliquer cette marque ? (o/N) : ")

                if reponse.lower() != 'o':
                    print("   ⏭️  Produit ignoré")
                    produits_ignores += 1
                    continue

            # Mettre à jour PRODUITS['marque'] avec le NOM de la marque
            cursor.execute(
                "UPDATE PRODUITS SET marque = ? WHERE id = ?",
                (nom_marque, produit_id)  # On met le NOM, pas l'ID
            )
            produits_mis_a_jour += 1
            print(f"   ✅ Produit mis à jour avec la marque: {nom_marque}")

        # 4. Valider les changements
        conn.commit()

        # 5. Résumé
        print("\n" + "=" * 80)
        print("📊 RÉSUMÉ FINAL :")
        print(f"   ✅ Produits mis à jour : {produits_mis_a_jour}")
        print(f"   ⏭️  Produits ignorés : {produits_ignores}")
        print(f"   ❌ Produits sans marque trouvée : {produits_non_trouves}")
        print(f"   📦 Total traités : {len(produits_sans_marque)}")

        # Vérifier combien restent sans marque
        cursor.execute("SELECT COUNT(*) FROM PRODUITS WHERE marque IS NULL")
        restants = cursor.fetchone()[0]
        print(f"   📌 Produits restants sans marque : {restants}")

        # Afficher un échantillon des produits mis à jour
        cursor.execute("""
            SELECT id, description, marque 
            FROM PRODUITS 
            WHERE marque IS NOT NULL 
            ORDER BY id DESC 
            LIMIT 5
        """)
        echantillon = cursor.fetchall()
        if echantillon:
            print("\n📌 Derniers produits mis à jour :")
            for prod_id, desc, marque in echantillon:
                print(f"   ID {prod_id}: {marque} <- {desc[:50]}...")

    except sqlite3.Error as e:
        print(f"❌ Erreur SQLite : {e}")
        conn.rollback()
    finally:
        conn.close()
        print("=" * 80)


def mise_a_jour_marques_automatique():
    """
    Version automatique sans validation (pour les cas où on veut tout appliquer)
    """
    conn = sqlite3.connect('EauVive_prix.db')
    cursor = conn.cursor()

    try:
        print("=" * 80)
        print("MISE À JOUR AUTOMATIQUE DES MARQUES")
        print("=" * 80)

        # Récupérer les marques
        cursor.execute("SELECT id, nom FROM MARQUES")
        marques = cursor.fetchall()
        print(f"📋 {len(marques)} marques chargées")

        # Récupérer les produits sans marque
        cursor.execute("""
            SELECT id, description 
            FROM PRODUITS 
            WHERE marque IS NULL AND description IS NOT NULL
        """)
        produits_sans_marque = cursor.fetchall()
        print(f"📦 {len(produits_sans_marque)} produits sans marque")
        print("-" * 80)

        produits_mis_a_jour = 0

        for produit_id, description in produits_sans_marque:
            description_lower = description.lower()

            # Chercher la première marque trouvée
            for marque_id, marque_nom in marques:
                if marque_nom.lower() in description_lower:
                    # Mettre à jour avec le NOM de la marque
                    cursor.execute(
                        "UPDATE PRODUITS SET marque = ? WHERE id = ?",
                        (marque_nom, produit_id)  # On met le NOM, pas l'ID
                    )
                    produits_mis_a_jour += 1
                    print(f"✅ Produit {produit_id} -> {marque_nom}")
                    break

        conn.commit()
        print("-" * 80)
        print(f"✅ {produits_mis_a_jour} produits mis à jour")

    except sqlite3.Error as e:
        print(f"❌ Erreur SQLite : {e}")
        conn.rollback()
    finally:
        conn.close()


def mise_a_jour_marques_avec_apercu():
    """
    Version avec aperçu global avant validation
    """
    conn = sqlite3.connect('EauVive_prix.db')
    cursor = conn.cursor()

    try:
        print("=" * 80)
        print("MISE À JOUR DES MARQUES - APERÇU GLOBAL")
        print("=" * 80)

        # Récupérer les marques
        cursor.execute("SELECT id, nom FROM MARQUES")
        marques = cursor.fetchall()

        # Récupérer les produits sans marque
        cursor.execute("""
            SELECT id, description 
            FROM PRODUITS 
            WHERE marque IS NULL AND description IS NOT NULL
        """)
        produits_sans_marque = cursor.fetchall()
        print(f"📦 {len(produits_sans_marque)} produits sans marque")
        print("-" * 80)

        # Afficher l'aperçu
        propositions = []

        for produit_id, description in produits_sans_marque:
            description_lower = description.lower()
            marques_trouvees = []

            for marque_id, marque_nom in marques:
                if marque_nom.lower() in description_lower:
                    marques_trouvees.append(marque_nom)

            if marques_trouvees:
                propositions.append((produit_id, description, marques_trouvees))
                print(f"📌 Produit {produit_id}:")
                print(f"   Description: {description[:100]}...")
                print(f"   Marques trouvées: {', '.join(marques_trouvees)}")
                print()

        if not propositions:
            print("❌ Aucune marque trouvée dans les descriptions")
            return

        print("=" * 80)
        print(f"📊 {len(propositions)} produits seront mis à jour")

        reponse = input("\nVoulez-vous appliquer ces modifications ? (o/N): ")

        if reponse.lower() == 'o':
            print("\n🔧 Application des modifications...")

            for produit_id, description, marques_trouvees in propositions:
                # Prendre la première marque trouvée
                nom_marque = marques_trouvees[0]
                cursor.execute(
                    "UPDATE PRODUITS SET marque = ? WHERE id = ?",
                    (nom_marque, produit_id)  # On met le NOM, pas l'ID
                )
                print(f"✅ Produit {produit_id} -> {nom_marque}")

            conn.commit()
            print(f"\n💾 {len(propositions)} modifications enregistrées")
        else:
            print("❌ Opération annulée")

    except sqlite3.Error as e:
        print(f"❌ Erreur SQLite : {e}")
        conn.rollback()
    finally:
        conn.close()


# Programme principal
if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("EauVive_prix.db - MISE À JOUR DES MARQUES")
    print("=" * 80)
    print("1. ✅ Validation ligne par ligne (recommandé)")
    print("2. ⚡ Exécution automatique (sans validation)")
    print("3. 👁️  Aperçu global avant validation")
    print("4. ❌ Quitter")

    choix = input("\nVotre choix (1-4) : ")

    if choix == "1":
        mise_a_jour_marques_validation_ligne()
    elif choix == "2":
        mise_a_jour_marques_automatique()
    elif choix == "3":
        mise_a_jour_marques_avec_apercu()
    else:
        print("Au revoir !")