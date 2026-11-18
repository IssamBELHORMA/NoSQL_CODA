# =====================================================================
# Lot 1 — Catalogue Produits (MongoDB)
# Création des collections, transformation des données brutes,
# avis clients et index
# Prérequis : avoir lancé import_raw.py (collections raw_*)
# Usage : python lot1-catalogue-mongodb/data.py
# =====================================================================

import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pprint import pprint

from pymongo import MongoClient

sys.stdout.reconfigure(encoding="utf-8")

db = MongoClient("mongodb://localhost:27017")["ldlc"]

# Repartir de zéro (les collections raw_* ne sont pas touchées)
db.produits.drop()
db.marques.drop()
db.avis.drop()


# Collection produits avec validation souple :
# champs communs obligatoires, champs supplémentaires autorisés

db.create_collection("produits", validator={
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["sku", "nom", "prix", "stock", "categorie"],
        "properties": {
            "sku":   {"bsonType": "string"},
            "nom":   {"bsonType": "string"},
            "prix":  {"bsonType": ["double", "int"], "minimum": 0},
            "stock": {"bsonType": "int", "minimum": 0},
            "categorie": {
                "bsonType": "object",
                "required": ["nom", "chemin"],
                "properties": {
                    "nom":    {"bsonType": "string"},
                    "chemin": {"bsonType": "array", "items": {"bsonType": "string"}}
                }
            }
        }
    }
})


# Transformation des données brutes -> produits

TAUX_USD_EUR = 0.92   # hypothèse : taux de conversion fixe

CATEGORIES = [
    {"raw": "raw_cpu",          "nom": "Processeurs",             "chemin": ["Composants", "Processeurs"],            "prefixe": "CPU"},
    {"raw": "raw_motherboard",  "nom": "Cartes mères",            "chemin": ["Composants", "Cartes mères"],           "prefixe": "MB"},
    {"raw": "raw_memory",       "nom": "Mémoire",                 "chemin": ["Composants", "Mémoire"],                "prefixe": "RAM"},
    {"raw": "raw_video_card",   "nom": "Cartes graphiques",       "chemin": ["Composants", "Cartes graphiques"],      "prefixe": "GPU"},
    {"raw": "raw_case",         "nom": "Boîtiers",                "chemin": ["Composants", "Boîtiers"],               "prefixe": "CASE"},
    {"raw": "raw_power_supply", "nom": "Alimentations",           "chemin": ["Composants", "Alimentations"],          "prefixe": "PSU"},
    {"raw": "raw_keyboard",     "nom": "Claviers",                "chemin": ["Périphériques", "Claviers"],            "prefixe": "KB"},
    {"raw": "raw_mouse",        "nom": "Souris",                  "chemin": ["Périphériques", "Souris"],              "prefixe": "MOUSE"},
    {"raw": "raw_monitor",      "nom": "Écrans",                  "chemin": ["Périphériques", "Écrans"],              "prefixe": "MON"},
    {"raw": "raw_headphones",   "nom": "Casques audio",           "chemin": ["Périphériques", "Casques audio"],       "prefixe": "HEAD"},
    {"raw": "raw_os",           "nom": "Systèmes d'exploitation", "chemin": ["Logiciels", "Systèmes d'exploitation"], "prefixe": "OS"},
]

# Marques dont le nom contient deux mots
MARQUES_DEUX_MOTS = ["Fractal Design", "Cooler Master", "Western Digital", "be quiet!",
                     "Lian Li", "Silicon Power", "Turtle Beach", "Mad Catz", "Red Hat", "Super Flower"]

# Index unique sur sku : nécessaire pour $merge (on: "sku")
db.produits.create_index("sku", unique=True)

CHAMPS_TECHNIQUES = ["_id", "name", "price", "_mots", "_deuxMots", "_marque", "_suffixe"]


def pipeline_transformation(c):
    return [
        # 1. Garder uniquement les produits avec un nom et un prix valides
        {"$match": {"name": {"$type": "string"}, "price": {"$type": "number", "$gt": 0}}},

        # 2. Extraire la marque à partir du nom
        {"$addFields": {"_mots": {"$split": ["$name", " "]}}},
        {"$addFields": {
            "_deuxMots": {"$concat": [
                {"$arrayElemAt": ["$_mots", 0]}, " ",
                {"$ifNull": [{"$arrayElemAt": ["$_mots", 1]}, ""]}
            ]}
        }},
        {"$addFields": {
            "_marque": {"$cond": [
                {"$in": ["$_deuxMots", MARQUES_DEUX_MOTS]},
                "$_deuxMots",
                {"$arrayElemAt": ["$_mots", 0]}
            ]},
            "_suffixe": {"$toUpper": {"$substrCP": [{"$toString": "$_id"}, 14, 10]}}
        }},

        # 3. Construire le document au format du modèle
        {"$project": {
            "_id": 0,
            "sku":  {"$concat": [c["prefixe"], "-", "$_suffixe"]},
            "nom":  "$name",
            "slug": {"$concat": [
                {"$replaceAll": {"input": {"$toLower": "$name"}, "find": " ", "replacement": "-"}},
                "-", {"$toLower": "$_suffixe"}
            ]},
            "prix":   {"$round": [{"$multiply": ["$price", TAUX_USD_EUR]}, 2]},
            "devise": {"$literal": "EUR"},
            "stock":  {"$toInt": {"$floor": {"$multiply": [{"$rand": {}}, 200]}}},
            "schema_version": {"$literal": 1},
            "categorie": {"$literal": {"nom": c["nom"], "chemin": c["chemin"]}},
            "marque": {
                "_id": {"$concat": ["M_", {"$toUpper": {"$replaceAll": {"input": "$_marque", "find": " ", "replacement": "_"}}}]},
                "nom": "$_marque"
            },
            # Attribute pattern : tous les champs spécifiques -> [{ k, v }]
            "specs": {
                "$map": {
                    "input": {
                        "$filter": {
                            "input": {"$objectToArray": "$$ROOT"},
                            "as": "a",
                            "cond": {"$and": [
                                {"$not": [{"$in": ["$$a.k", CHAMPS_TECHNIQUES]}]},
                                {"$ne": ["$$a.v", None]}
                            ]}
                        }
                    },
                    "as": "a",
                    "in": {"k": "$$a.k", "v": "$$a.v"}
                }
            },
            "stats_avis":   {"$literal": {"nb": 0, "somme": 0, "moyenne": None}},
            "avis_recents": {"$literal": []},
            "compatibles":  {"$literal": []},
            "source": {"dataset": {"$literal": "pc-part-dataset"},
                       "raw_collection": {"$literal": c["raw"]},
                       "raw_id": "$_id"}
        }},

        # 4. Écrire dans produits (le validateur $jsonSchema s'applique)
        {"$merge": {"into": "produits", "on": "sku", "whenMatched": "replace", "whenNotMatched": "insert"}}
    ]


for c in CATEGORIES:
    db[c["raw"]].aggregate(pipeline_transformation(c))


# Référentiel des marques, généré à partir des produits

db.produits.aggregate([
    {"$group": {
        "_id": "$marque._id",
        "nom": {"$first": "$marque.nom"},
        "nb_produits": {"$sum": 1},
        "categories": {"$addToSet": "$categorie.nom"}
    }},
    {"$sort": {"nb_produits": -1}},
    {"$out": "marques"}
])


# Avis clients (données de test générées)

NB_PRODUITS_AVEC_AVIS = 3000
NOTES = [5, 5, 5, 5, 4, 4, 4, 3, 3, 2, 1]   # répartition réaliste
TITRES = {
    5: ["Excellent produit", "Parfait", "Je recommande"],
    4: ["Très bon produit", "Bon rapport qualité/prix", "Satisfait"],
    3: ["Correct", "Moyen", "Peut mieux faire"],
    2: ["Décevant", "Qualité moyenne"],
    1: ["À éviter", "Très déçu"],
}
TEXTES = {
    5: ["Conforme à la description, je recommande.", "Rien à redire, livraison rapide."],
    4: ["Très bien dans l'ensemble, quelques petits défauts.", "Bon produit pour le prix."],
    3: ["Fait le travail, sans plus.", "Correct mais j'attendais mieux."],
    2: ["Plusieurs problèmes après quelques semaines.", "Finitions décevantes."],
    1: ["Produit défectueux, retourné.", "Ne correspond pas à la description."],
}
DEUX_ANS = timedelta(days=2 * 365)
maintenant = datetime.now(timezone.utc)

# 1. Générer les avis pour un échantillon de produits
cibles = list(db.produits.aggregate([
    {"$sample": {"size": NB_PRODUITS_AVEC_AVIS}},
    {"$project": {"_id": 1, "sku": 1}}
]))

lot = []
for p in cibles:
    for _ in range(random.randint(1, 15)):
        note = random.choice(NOTES)
        lot.append({
            "produit_id": p["_id"],
            "sku": p["sku"],
            "client": f"client_{random.randint(0, 99999):05d}",
            "note": note,
            "titre": random.choice(TITRES[note]),
            "texte": random.choice(TEXTES[note]),
            "date": maintenant - DEUX_ANS * random.random(),
            "genere": True,
        })
    if len(lot) >= 1000:          # insertion par lots
        db.avis.insert_many(lot)
        lot = []
if lot:
    db.avis.insert_many(lot)

# 2. Subset pattern + Computed pattern : mettre à jour les fiches produits
db.avis.aggregate([
    {"$sort": {"produit_id": 1, "date": -1}},
    {"$group": {
        "_id": "$produit_id",
        "nb": {"$sum": 1},
        "somme": {"$sum": "$note"},
        "recents": {"$firstN": {"n": 5, "input": {
            "client": "$client", "note": "$note", "titre": "$titre", "date": "$date"}}}
    }},
    {"$project": {
        "stats_avis": {"nb": "$nb", "somme": "$somme",
                       "moyenne": {"$round": [{"$divide": ["$somme", "$nb"]}, 2]}},
        "avis_recents": "$recents"
    }},
    {"$merge": {"into": "produits", "on": "_id", "whenMatched": "merge", "whenNotMatched": "discard"}}
])


# Index (l'index unique sur sku a été créé avant le $merge)

db.produits.create_index("slug", unique=True)
db.produits.create_index([("categorie.chemin", 1), ("prix", 1)])
db.produits.create_index([("specs.k", 1), ("specs.v", 1)])
db.produits.create_index([("marque.nom", 1), ("prix", 1)])
db.produits.create_index([("nom", "text")], default_language="none")
db.avis.create_index([("produit_id", 1), ("date", -1)])


def plan(curseur):
    """Résumé d'un plan d'exécution : étapes utilisées et documents examinés."""
    e = curseur.explain()
    texte_plan = json.dumps(e["queryPlanner"]["winningPlan"], default=str)
    return {
        "etapes": re.findall(r'"stage": "([A-Z_]+)"', texte_plan),
        "documents_examines": e["executionStats"]["totalDocsExamined"],
        "resultats": e["executionStats"]["nReturned"],
    }



# Vérification

un_avis = db.avis.find_one()

pprint({
    "produits": db.produits.count_documents({}),
    "marques": db.marques.count_documents({}),
    "avis": db.avis.count_documents({}),
    "produits_avec_avis": db.produits.count_documents({"stats_avis.nb": {"$gt": 0}}),
    "index_produits": [i["name"] for i in db.produits.list_indexes()],
    "index_avis": [i["name"] for i in db.avis.list_indexes()],
    "plans": {
        "categorie_triee_par_prix": plan(
            db.produits.find({"categorie.chemin": "Processeurs"}).sort("prix", 1).limit(20)),
        "filtre_spec": plan(
            db.produits.find({"specs": {"$elemMatch": {"k": "microarchitecture", "v": "Zen 4"}}})),
        "recherche_texte": plan(
            db.produits.find({"$text": {"$search": "ryzen"}})),
        "avis_produit": plan(
            db.avis.find({"produit_id": un_avis["produit_id"]}).sort("date", -1)),
    },
}, sort_dicts=False)