# =====================================================================
# Lot 4 — Recommandations (Neo4j) : import des produits depuis MongoDB
# Prérequis : catalogue du Lot 1 chargé (data.py)
# Usage : python lot4-reco-neo4j/import_graphe.py
# =====================================================================

import sys

from neo4j import GraphDatabase
from pymongo import MongoClient

sys.stdout.reconfigure(encoding="utf-8")

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))
catalogue = MongoClient("mongodb://localhost:27017")["ldlc"]["produits"]

# Repartir de zéro + contraintes d'unicité (qui créent aussi les index)
driver.execute_query("MATCH (n) DETACH DELETE n")
for label, cle in [("Produit", "sku"), ("Marque", "nom"), ("Categorie", "nom")]:
    driver.execute_query(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{cle} IS UNIQUE")

# Produits, marques et catégories (seulement les champs utiles aux recommandations)
produits = [{
    "sku": p["sku"],
    "nom": p["nom"],
    "prix": p["prix"],
    "categorie": p["categorie"]["nom"],
    "marque": p["marque"]["nom"],
} for p in catalogue.find({}, {"sku": 1, "nom": 1, "prix": 1, "categorie.nom": 1, "marque.nom": 1})]

for i in range(0, len(produits), 1000):          # import par lots de 1000
    driver.execute_query("""
        UNWIND $lot AS p
        MERGE (prod:Produit {sku: p.sku})
        SET prod.nom = p.nom, prod.prix = p.prix
        MERGE (m:Marque {nom: p.marque})
        MERGE (c:Categorie {nom: p.categorie})
        MERGE (prod)-[:DE_MARQUE]->(m)
        MERGE (prod)-[:DANS]->(c)
    """, lot=produits[i:i + 1000])

print(len(produits), "produits importés")
