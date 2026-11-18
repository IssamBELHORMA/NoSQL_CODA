# =====================================================================
# Lot 3 — Requêtes analytiques (Cassandra)
# Prérequis : generer_logs.py et commandes.py exécutés
# Usage : python lot3-logs-cassandra/requetes.py
# =====================================================================

import sys
from collections import Counter
from datetime import date, timedelta

from pymongo import MongoClient

from client_cassandra import get_session

sys.stdout.reconfigure(encoding="utf-8")

session = get_session()
catalogue = MongoClient("mongodb://localhost:27017")["ldlc"]["produits"]
aujourdhui = date.today()


def nom(sku):
    p = catalogue.find_one({"sku": sku}, {"nom": 1})
    return p["nom"] if p else sku


# R1 — Top 10 des produits consultés cette semaine
# 7 partitions lues (une par jour), puis addition et tri en Python
vues_semaine = Counter()
for i in range(7):
    jour = aujourdhui - timedelta(days=i)
    for l in session.execute("SELECT sku, vues FROM vues_par_jour WHERE jour = %s", [jour]):
        vues_semaine[l.sku] += l.vues

print("===== R1 - Top 10 des produits consultés cette semaine =====")
for sku, vues in vues_semaine.most_common(10):
    print(vues, "vues -", nom(sku))

# R2 — Vues d'un produit aujourd'hui et sur les derniers jours (une seule partition)
sku = vues_semaine.most_common(1)[0][0]
print(f"\n===== R2 - Vues de {nom(sku)} =====")
l = session.execute("SELECT vues FROM vues_par_produit WHERE sku = %s AND jour = %s",
                    [sku, aujourdhui]).one()
print("Aujourd'hui :", l.vues if l else 0)
for l in session.execute("SELECT jour, vues FROM vues_par_produit WHERE sku = %s LIMIT 7", [sku]):
    print(" ", l.jour, ":", l.vues)

# R3 — Recherches les plus fréquentes aujourd'hui (on lit les 10 buckets du jour)
recherches = Counter()
for bucket in range(10):
    for l in session.execute("SELECT recherche FROM evenements_par_jour WHERE jour = %s AND bucket = %s",
                             [aujourdhui, bucket]):
        if l.recherche:
            recherches[l.recherche] += 1

print("\n===== R3 - Top recherches du jour =====")
for terme, nb in recherches.most_common(5):
    print(nb, "-", terme)

# R4 — Historique des commandes d'un client (une partition, déjà triée par date)
print("\n===== R4 - Commandes du client U1024 =====")
for c in session.execute("SELECT date_commande, total, lignes FROM commandes_par_client "
                         "WHERE user_id = %s LIMIT 10", ["U1024"]):
    print(c.date_commande.date(), "-", c.total, "€ -", ", ".join(nom(s) for s in c.lignes))
