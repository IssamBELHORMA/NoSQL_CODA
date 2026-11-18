# =====================================================================
# Lot 3 — Historique des commandes (Cassandra)
# Prérequis : catalogue du Lot 1 chargé, schéma créé (client_cassandra.py)
# Usage : python lot3-logs-cassandra/commandes.py
# =====================================================================

import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from cassandra import ConsistencyLevel
from pymongo import MongoClient

from client_cassandra import get_session

sys.stdout.reconfigure(encoding="utf-8")

NB_COMMANDES = 3000
catalogue = MongoClient("mongodb://localhost:27017")["ldlc"]["produits"]
session = get_session()

insert_commande = session.prepare(
    "INSERT INTO commandes_par_client (user_id, date_commande, commande_id, total, lignes) "
    "VALUES (?, ?, ?, ?, ?)")
# Une commande est une donnée importante : on attend la confirmation d'une majorité de réplicas
insert_commande.consistency_level = ConsistencyLevel.LOCAL_QUORUM


def enregistrer_commande(user_id, lignes, date=None):
    """Enregistre une commande validée (lignes = {sku: quantité}, ex. panier Redis du Lot 2).
    Les prix sont lus dans MongoDB au moment de la commande, puis figés."""
    prix = {p["sku"]: p["prix"] for p in catalogue.find({"sku": {"$in": list(lignes)}}, {"sku": 1, "prix": 1})}
    total = sum(Decimal(str(prix[s])) * q for s, q in lignes.items())
    session.execute(insert_commande, (user_id, date or datetime.now(timezone.utc),
                                      uuid.uuid4(), total, lignes))
    return total


def historique(user_id, limite=10):
    """Historique des commandes d'un client : une seule partition, déjà triée."""
    return list(session.execute(
        "SELECT date_commande, total, lignes FROM commandes_par_client WHERE user_id = %s LIMIT %s",
        (user_id, limite)))


def produits_populaires(categorie, filtre={}, n=15):
    return [p["sku"] for p in catalogue.find({"categorie.nom": categorie, **filtre}, {"sku": 1})
            .sort("stats_avis.nb", -1).limit(n)]


# Génération de commandes de test : des configurations PC AM5 (processeur + carte mère + mémoire...)
if __name__ == "__main__":
    pools = {c: produits_populaires(c) for c in
             ["Mémoire", "Cartes graphiques", "Boîtiers", "Alimentations"]}
    pools["Processeurs"] = produits_populaires("Processeurs", {"specs": {"$elemMatch": {"k": "microarchitecture", "v": "Zen 4"}}})
    pools["Cartes mères"] = produits_populaires("Cartes mères", {"specs": {"$elemMatch": {"k": "socket", "v": "AM5"}}})
    pools["Processeurs"].append(catalogue.find_one({"nom": "AMD Ryzen 7 7800X3D"})["sku"])

    maintenant = datetime.now(timezone.utc)
    for _ in range(NB_COMMANDES):
        categories = random.sample(list(pools), random.randint(2, 4))
        lignes = {random.choice(pools[c]): 1 for c in categories}
        enregistrer_commande(f"U{random.randint(1000, 5999)}", lignes,
                             maintenant - timedelta(days=365) * random.random())

    carte_mere_am5 = catalogue.find_one({"specs": {"$elemMatch": {"k": "socket", "v": "AM5"}}})["sku"]
    enregistrer_commande("U1024", {pools["Processeurs"][-1]: 1, carte_mere_am5: 1})
    print(f"{NB_COMMANDES + 1} commandes enregistrées")
    print("\nHistorique de U1024 :")
    for c in historique("U1024"):
        print(f" - {c.date_commande:%Y-%m-%d}  {c.total} €  {dict(c.lignes)}")
