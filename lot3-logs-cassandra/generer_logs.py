# =====================================================================
# Lot 3 — Génération d'événements de navigation (données de test)
# Prérequis : catalogue du Lot 1 chargé, schéma créé (client_cassandra.py)
# Usage : python lot3-logs-cassandra/generer_logs.py
# =====================================================================

import random
import sys
from datetime import datetime, timedelta, timezone

from cassandra.concurrent import execute_concurrent_with_args
from cassandra.util import uuid_from_time
from pymongo import MongoClient

from client_cassandra import get_session

sys.stdout.reconfigure(encoding="utf-8")

NB_EVENEMENTS = 50_000
NB_JOURS = 7
NB_BUCKETS = 10
RECHERCHES = ["rtx 4070", "ryzen 7", "clavier mécanique", "ssd 1to", "écran 144hz", "souris sans fil"]

session = get_session()
skus = [p["sku"] for p in MongoClient("mongodb://localhost:27017")["ldlc"]["produits"].find({}, {"sku": 1})]

# Quelques produits très consultés, beaucoup peu consultés (comme sur un vrai site)
random.shuffle(skus)
poids = [1 / (i + 1) for i in range(len(skus))]

insert_evenement = session.prepare(
    "INSERT INTO evenements_par_jour (jour, bucket, ts, type, user_id, session_id, sku, recherche) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
incr_produit = session.prepare("UPDATE vues_par_produit SET vues = vues + 1 WHERE sku = ? AND jour = ?")
incr_jour = session.prepare("UPDATE vues_par_jour SET vues = vues + 1 WHERE jour = ? AND sku = ?")


def evenement_aleatoire(maintenant):
    date = maintenant - timedelta(days=NB_JOURS) * random.random()
    session_id = f"sess-{random.randint(0, 9999)}"
    user_id = random.choice(["", f"U{random.randint(1000, 5999)}"])   # connecté ou non
    type_ev = random.choices(["vue", "clic", "recherche"], weights=[70, 20, 10])[0]
    sku = random.choices(skus, weights=poids)[0] if type_ev != "recherche" else None
    recherche = random.choice(RECHERCHES) if type_ev == "recherche" else None
    return (date.date(), random.randrange(NB_BUCKETS), uuid_from_time(date),
            type_ev, user_id, session_id, sku, recherche)


if __name__ == "__main__":
    maintenant = datetime.now(timezone.utc)
    evenements = [evenement_aleatoire(maintenant) for _ in range(NB_EVENEMENTS)]

    # Chaque événement est écrit dans le journal ; chaque vue incrémente aussi les compteurs
    execute_concurrent_with_args(session, insert_evenement, evenements, concurrency=100)
    vues = [(e[6], e[0]) for e in evenements if e[3] == "vue"]
    execute_concurrent_with_args(session, incr_produit, vues, concurrency=100)
    execute_concurrent_with_args(session, incr_jour, [(j, s) for s, j in vues], concurrency=100)

    print(f"{len(evenements)} événements écrits, dont {len(vues)} vues de produits")
