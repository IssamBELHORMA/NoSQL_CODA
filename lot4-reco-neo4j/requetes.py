# =====================================================================
# Lot 4 — Requêtes de recommandation (Cypher)
# Prérequis : import_graphe.py, compatibilites.py et achats.py exécutés
# Usage : python lot4-reco-neo4j/requetes.py
# =====================================================================

import sys

from neo4j import GraphDatabase

sys.stdout.reconfigure(encoding="utf-8")

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))


def afficher(titre, requete, **params):
    print(f"\n===== {titre} =====")
    for r in driver.execute_query(requete, params).records:
        print(" | ".join(str(v) for v in r.values()))


CPU = "AMD Ryzen 7 7800X3D"

# R1 — « Les clients qui ont acheté ce processeur ont aussi acheté cette carte mère »
afficher("R1 - Cartes mères achetées avec le " + CPU, """
    MATCH (cpu:Produit {nom: $cpu})-[r:ACHETE_AVEC]-(mb:Produit)-[:DANS]->(:Categorie {nom: 'Cartes mères'})
    RETURN mb.nom, r.nb AS fois
    ORDER BY fois DESC LIMIT 5
""", cpu=CPU)

# R2 — Même question, en parcourant les clients (sans relation pré-calculée)
afficher("R2 - Autres produits achetés par les clients du " + CPU, """
    MATCH (cpu:Produit {nom: $cpu})<-[:A_ACHETE]-(c:Client)-[:A_ACHETE]->(autre:Produit)
    WHERE autre <> cpu
    RETURN autre.nom, count(DISTINCT c) AS clients
    ORDER BY clients DESC LIMIT 5
""", cpu=CPU)

# R3 — Cartes mères compatibles avec ce processeur (même socket)
afficher("R3 - Cartes mères compatibles avec le " + CPU, """
    MATCH (cpu:Produit {nom: $cpu})-[:SOCKET]->(s:Socket)<-[:SOCKET]-(mb:Produit)
          -[:DANS]->(:Categorie {nom: 'Cartes mères'})
    RETURN DISTINCT s.nom AS socket, mb.nom, mb.prix
    ORDER BY mb.prix LIMIT 5
""", cpu=CPU)

# R4 — « Produits compatibles avec ce boîtier » : cartes mères (format), puis processeurs (socket)
boitier = driver.execute_query(
    "MATCH (b:Produit)-[:ACCEPTE]->(:Format {nom: 'Mini ITX'}) WHERE NOT (b)-[:ACCEPTE]->(:Format {nom: 'ATX'}) "
    "RETURN b.nom AS nom LIMIT 1").records[0]["nom"]
afficher("R4a - Cartes mères compatibles avec le boîtier " + boitier, """
    MATCH (b:Produit {nom: $boitier})-[:ACCEPTE]->(f:Format)<-[:FORMAT]-(mb:Produit)
    RETURN DISTINCT f.nom AS format, mb.nom, mb.prix
    ORDER BY mb.prix LIMIT 5
""", boitier=boitier)

afficher("R4b - Processeurs AM5 utilisables dans ce boîtier (4 sauts)", """
    MATCH (b:Produit {nom: $boitier})-[:ACCEPTE]->(:Format)<-[:FORMAT]-(mb:Produit)
          -[:SOCKET]->(s:Socket {nom: 'AM5'})<-[:SOCKET]-(cpu:Produit)-[:DANS]->(:Categorie {nom: 'Processeurs'})
    RETURN DISTINCT cpu.nom, cpu.prix
    ORDER BY cpu.prix DESC LIMIT 5
""", boitier=boitier)

# R5 — Produits similaires : même catégorie, même marque, prix à ±20 %
afficher("R5 - Produits similaires au " + CPU, """
    MATCH (p:Produit {nom: $cpu})-[:DANS]->(c:Categorie)<-[:DANS]-(autre:Produit)-[:DE_MARQUE]->(m:Marque),
          (p)-[:DE_MARQUE]->(m)
    WHERE autre <> p AND autre.prix >= p.prix * 0.8 AND autre.prix <= p.prix * 1.2
    RETURN DISTINCT autre.nom, autre.prix, round(abs(autre.prix - p.prix), 2) AS ecart
    ORDER BY ecart LIMIT 5
""", cpu=CPU)

# R6 — Recommandations pour un client : produits achetés avec ses achats, qu'il n'a pas encore
afficher("R6 - Recommandations pour le client U1024", """
    MATCH (c:Client {id: 'U1024'})-[:A_ACHETE]->(p:Produit)-[r:ACHETE_AVEC]-(reco:Produit)
    WHERE NOT (c)-[:A_ACHETE]->(reco)
    RETURN reco.nom, sum(r.nb) AS score
    ORDER BY score DESC LIMIT 5
""")
