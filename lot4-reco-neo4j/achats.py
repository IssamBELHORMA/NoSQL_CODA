# =====================================================================
# Lot 4 — Achats croisés à partir des commandes (Cassandra -> Neo4j)
# Batch nocturne : relit les commandes du Lot 3 et met à jour le graphe
# Prérequis : import_graphe.py et lot3-logs-cassandra/commandes.py exécutés
# Usage : python lot4-reco-neo4j/achats.py
# =====================================================================

import sys

from cassandra.cluster import Cluster
from neo4j import GraphDatabase

sys.stdout.reconfigure(encoding="utf-8")

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))
cassandra = Cluster(["localhost"], port=9042).connect("ldlc_logs")

# Lecture de toutes les commandes (parcours complet de la table : acceptable pour un batch)
commandes = [{"client": c.user_id, "skus": list(c.lignes)}
             for c in cassandra.execute("SELECT user_id, lignes FROM commandes_par_client")]

driver.execute_query("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Client) REQUIRE c.id IS UNIQUE")
driver.execute_query("MATCH ()-[r:A_ACHETE|ACHETE_AVEC]->() DELETE r")

# 1. (:Client)-[:A_ACHETE]->(:Produit)
for i in range(0, len(commandes), 500):
    driver.execute_query("""
        UNWIND $lot AS cmd
        MERGE (c:Client {id: cmd.client})
        WITH c, cmd
        UNWIND cmd.skus AS sku
        MATCH (p:Produit {sku: sku})
        MERGE (c)-[a:A_ACHETE]->(p)
        ON CREATE SET a.nb = 1 ON MATCH SET a.nb = a.nb + 1
    """, lot=commandes[i:i + 500])

# 2. (:Produit)-[:ACHETE_AVEC {nb}]->(:Produit) : produits présents dans une même commande
paires = {}
for cmd in commandes:
    skus = sorted(cmd["skus"])
    for i in range(len(skus)):
        for j in range(i + 1, len(skus)):
            paires[(skus[i], skus[j])] = paires.get((skus[i], skus[j]), 0) + 1

driver.execute_query("""
    UNWIND $paires AS p
    MATCH (a:Produit {sku: p.a}), (b:Produit {sku: p.b})
    MERGE (a)-[r:ACHETE_AVEC]-(b)
    SET r.nb = p.nb
""", paires=[{"a": a, "b": b, "nb": nb} for (a, b), nb in paires.items()])

print(len(commandes), "commandes importées,", len(paires), "paires de produits achetés ensemble")
