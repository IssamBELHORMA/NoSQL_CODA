# =====================================================================
# Lot 2 — Panier (Redis), avec les prix lus dans le catalogue (MongoDB)
# Prérequis : catalogue du Lot 1 chargé (data.py)
# Usage : python lot2-panier-redis/panier.py
# =====================================================================

import sys
import time

from pymongo import MongoClient

from client_redis import get_client

sys.stdout.reconfigure(encoding="utf-8")

TTL_PANIER = 24 * 3600   # 24 heures d'inactivité


def cle_panier(panier_id):
    return f"panier:{panier_id}"


def ajouter(r, panier_id, sku, quantite=1):
    """Ajoute un article (ou augmente sa quantité) et prolonge le TTL."""
    pipe = r.pipeline(transaction=True)
    pipe.hincrby(cle_panier(panier_id), sku, quantite)
    pipe.expire(cle_panier(panier_id), TTL_PANIER)
    return pipe.execute()[0]                       # nouvelle quantité


def retirer(r, panier_id, sku, quantite=1):
    """Diminue la quantité ; supprime la ligne si elle tombe à 0."""
    reste = r.hincrby(cle_panier(panier_id), sku, -quantite)
    if reste <= 0:
        r.hdel(cle_panier(panier_id), sku)
    r.expire(cle_panier(panier_id), TTL_PANIER)
    return max(reste, 0)


def lire(r, panier_id):
    """Contenu brut du panier {sku: quantité}, avec TTL glissant."""
    pipe = r.pipeline(transaction=True)
    pipe.hgetall(cle_panier(panier_id))
    pipe.expire(cle_panier(panier_id), TTL_PANIER)
    contenu = pipe.execute()[0]
    return {sku: int(q) for sku, q in contenu.items()}


def lire_detaille(r, catalogue, panier_id):
    """Panier avec noms et prix lus dans MongoDB (source de vérité des prix)."""
    contenu = lire(r, panier_id)
    produits = {p["sku"]: p for p in catalogue.find(
        {"sku": {"$in": list(contenu)}}, {"_id": 0, "sku": 1, "nom": 1, "prix": 1})}

    lignes = []
    for sku, quantite in contenu.items():
        p = produits.get(sku)
        if p:
            lignes.append({"sku": sku, "nom": p["nom"], "prix": p["prix"],
                           "quantite": quantite, "sous_total": round(p["prix"] * quantite, 2)})
    return {"lignes": lignes, "total": round(sum(l["sous_total"] for l in lignes), 2)}


def fusionner(r, id_anonyme, id_utilisateur):
    """À la connexion : le panier du visiteur anonyme rejoint celui du compte."""
    source, cible = cle_panier(id_anonyme), cle_panier(id_utilisateur)
    contenu = r.hgetall(source)

    pipe = r.pipeline(transaction=True)
    for sku, quantite in contenu.items():
        pipe.hincrby(cible, sku, int(quantite))
    pipe.expire(cible, TTL_PANIER)
    pipe.delete(source)
    pipe.execute()


def valider_commande(r, catalogue, panier_id):
    """Calcule le total puis vide le panier.
    (L'enregistrement de la commande relève du Lot 3, Cassandra.)"""
    commande = lire_detaille(r, catalogue, panier_id)
    r.delete(cle_panier(panier_id))
    return commande



# Démonstration
if __name__ == "__main__":
    r = get_client()
    catalogue = MongoClient("mongodb://localhost:27017")["ldlc"]["produits"]

    # Trois vrais produits du catalogue
    cpu = catalogue.find_one({"nom": "AMD Ryzen 7 7800X3D"}, {"sku": 1})["sku"]
    carte_mere = catalogue.find_one({"categorie.nom": "Cartes mères"}, {"sku": 1})["sku"]
    memoire = catalogue.find_one({"categorie.nom": "Mémoire"}, {"sku": 1})["sku"]

    ID_ANONYME = "sess-demo-anonyme"   # visiteur non connecté : identifiant de session
    ID_ALICE = "U1024"                 # utilisateur connecté : identifiant du compte
    r.delete(cle_panier(ID_ANONYME), cle_panier(ID_ALICE))   # relançable

    print("===== 1. Visiteur anonyme : ajout d'articles =====")
    ajouter(r, ID_ANONYME, cpu)
    ajouter(r, ID_ANONYME, memoire, 2)
    print("Contenu brut (Redis) :", lire(r, ID_ANONYME))
    print("TTL :", r.ttl(cle_panier(ID_ANONYME)), "secondes")

    print("\n===== 2. Affichage avec les prix du catalogue (MongoDB) =====")
    print(lire_detaille(r, catalogue, ID_ANONYME))

    print("\n===== 3. Modification des quantités =====")
    print("Mémoire +1 ->", ajouter(r, ID_ANONYME, memoire))
    print("Mémoire -3 ->", retirer(r, ID_ANONYME, memoire, 3), "(ligne supprimée)")
    print("Contenu :", lire(r, ID_ANONYME))

    print("\n===== 4. Connexion : fusion avec le panier du compte =====")
    ajouter(r, ID_ALICE, carte_mere)               # panier déjà existant sur le compte
    fusionner(r, ID_ANONYME, ID_ALICE)
    print("Panier d'Alice :", lire(r, ID_ALICE))
    print("Panier anonyme supprimé :", r.exists(cle_panier(ID_ANONYME)) == 0)

    print("\n===== 5. Expiration automatique (TTL de 3 secondes) =====")
    ajouter(r, "sess-demo-abandon", cpu)
    r.expire(cle_panier("sess-demo-abandon"), 3)
    time.sleep(4)
    print("Panier abandonné après 4 secondes :", lire(r, "sess-demo-abandon"))

    print("\n===== 6. Validation de la commande =====")
    print("Commande :", valider_commande(r, catalogue, ID_ALICE))
    print("Panier vidé :", r.exists(cle_panier(ID_ALICE)) == 0)