# =====================================================================
# Lot 4 — Relations de compatibilité (socket, format de carte mère)
# Prérequis : import_graphe.py exécuté
# Usage : python lot4-reco-neo4j/compatibilites.py
# =====================================================================

import sys

from neo4j import GraphDatabase
from pymongo import MongoClient

sys.stdout.reconfigure(encoding="utf-8")

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))
catalogue = MongoClient("mongodb://localhost:27017")["ldlc"]["produits"]

# Le dataset ne donne pas le socket des processeurs : on le déduit de la microarchitecture
SOCKET_CPU = {
    "Zen 5": "AM5", "Zen 4": "AM5",
    "Zen 3": "AM4", "Zen 2": "AM4", "Zen+": "AM4", "Zen": "AM4",
    "Arrow Lake": "LGA1851",
    "Raptor Lake Refresh": "LGA1700", "Raptor Lake": "LGA1700", "Alder Lake": "LGA1700",
    "Rocket Lake": "LGA1200", "Comet Lake": "LGA1200",
    "Coffee Lake Refresh": "LGA1151", "Coffee Lake": "LGA1151", "Kaby Lake": "LGA1151", "Skylake": "LGA1151",
    "Haswell": "LGA1150", "Broadwell": "LGA1150",
}

# Formats de carte mère acceptés par chaque type de boîtier
FORMATS_BOITIER = {
    "ATX Full Tower": ["EATX", "ATX", "Micro ATX", "Mini ITX"],
    "ATX Mid Tower": ["ATX", "Micro ATX", "Mini ITX"],
    "MicroATX Mid Tower": ["Micro ATX", "Mini ITX"],
    "MicroATX Mini Tower": ["Micro ATX", "Mini ITX"],
    "Mini ITX Tower": ["Mini ITX"],
    "Mini ITX Desktop": ["Mini ITX"],
}


def spec(produit, cle):
    for s in produit.get("specs", []):
        if s["k"] == cle:
            return s["v"]


def produits(categorie):
    return list(catalogue.find({"categorie.nom": categorie}, {"sku": 1, "specs": 1}))


# 1. Processeurs et cartes mères -> (:Socket)
liens_socket = [{"sku": p["sku"], "socket": SOCKET_CPU.get(spec(p, "microarchitecture"))}
                for p in produits("Processeurs")]
liens_socket += [{"sku": p["sku"], "socket": spec(p, "socket")} for p in produits("Cartes mères")]

driver.execute_query("""
    UNWIND $liens AS l
    MATCH (p:Produit {sku: l.sku})
    MERGE (s:Socket {nom: l.socket})
    MERGE (p)-[:SOCKET]->(s)
""", liens=[l for l in liens_socket if l["socket"]])

# 2. Cartes mères -> (:Format) <- boîtiers
liens_format = [{"sku": p["sku"], "format": spec(p, "form_factor"), "relation": "FORMAT"}
                for p in produits("Cartes mères")]
for p in produits("Boîtiers"):
    for f in FORMATS_BOITIER.get(spec(p, "type"), []):
        liens_format.append({"sku": p["sku"], "format": f, "relation": "ACCEPTE"})

for relation in ["FORMAT", "ACCEPTE"]:
    driver.execute_query(f"""
        UNWIND $liens AS l
        MATCH (p:Produit {{sku: l.sku}})
        MERGE (f:Format {{nom: l.format}})
        MERGE (p)-[:{relation}]->(f)
    """, liens=[l for l in liens_format if l["format"] and l["relation"] == relation])

nb = driver.execute_query("MATCH ()-[r:SOCKET|FORMAT|ACCEPTE]->() RETURN count(r) AS nb").records[0]["nb"]
print(nb, "relations de compatibilité créées")
