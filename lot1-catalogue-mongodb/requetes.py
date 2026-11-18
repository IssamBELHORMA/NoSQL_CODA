# =====================================================================
# Lot 1 — Catalogue Produits (MongoDB) : requêtes types
# Prérequis : avoir exécuté data.py
# Usage : python lot1-catalogue-mongodb/requetes.py
# =====================================================================

import sys
from datetime import datetime, timezone
from pprint import pprint

from pymongo import MongoClient

sys.stdout.reconfigure(encoding="utf-8")

db = MongoClient("mongodb://localhost:27017")["ldlc"]


def afficher(titre, valeur):
    print(f"\n===== {titre} =====")
    pprint(valeur, sort_dicts=False)


# Produit de référence pour les exemples
ref = db.produits.find_one({"nom": "AMD Ryzen 7 7800X3D"})

# R1 — Fiche produit complète, en une seule lecture (index slug)
afficher("R1 - Fiche produit", db.produits.find_one(
    {"slug": ref["slug"]},
    {"_id": 0, "source": 0}
))

# R2 — Catégorie Processeurs, page 2 (10 par page), prix croissant
PAGE, TAILLE_PAGE = 2, 10
afficher("R2 - Processeurs, page 2", list(db.produits.find(
    {"categorie.chemin": "Processeurs"},
    {"_id": 0, "nom": 1, "prix": 1, "marque.nom": 1, "stats_avis.moyenne": 1}
).sort("prix", 1).skip((PAGE - 1) * TAILLE_PAGE).limit(TAILLE_PAGE)))

# R3 — Filtres techniques (attribute pattern)
# Processeurs d'au moins 8 cœurs, microarchitecture Zen 4
afficher("R3a - CPU >= 8 cœurs, Zen 4", list(db.produits.find(
    {"specs": {"$all": [
        {"$elemMatch": {"k": "core_count", "v": {"$gte": 8}}},
        {"$elemMatch": {"k": "microarchitecture", "v": "Zen 4"}}
    ]}},
    {"_id": 0, "nom": 1, "prix": 1}
).sort("prix", 1).limit(5)))

# Claviers sans fil rétroéclairés RGB : même requête, même index, autre catégorie
afficher("R3b - Claviers sans fil RGB", list(db.produits.find(
    {"specs": {"$all": [
        {"$elemMatch": {"k": "connection_type", "v": "Wireless"}},
        {"$elemMatch": {"k": "backlit", "v": "RGB"}}
    ]}},
    {"_id": 0, "nom": 1, "prix": 1}
).sort("prix", 1).limit(5)))

# R4 — Recherche texte, triée par pertinence
afficher("R4 - Recherche 'ryzen 7'", list(db.produits.find(
    {"$text": {"$search": "ryzen 7"}},
    {"_id": 0, "nom": 1, "prix": 1, "score": {"$meta": "textScore"}}
).sort([("score", {"$meta": "textScore"})]).limit(5)))

# R5 — Marque + budget (extended reference : pas de jointure)
afficher("R5 - Corsair à moins de 100 €", list(db.produits.find(
    {"marque.nom": "Corsair", "prix": {"$lte": 100}},
    {"_id": 0, "nom": 1, "prix": 1, "categorie.nom": 1}
).sort("prix", -1).limit(5)))

# R6 — Évolution sans migration
# a) Nouvel attribut sur une fiche existante (+ version de schéma)
db.produits.update_one(
    {"_id": ref["_id"]},
    {"$addToSet": {"specs": {"k": "pcie_version", "v": "5.0"}}, "$set": {"schema_version": 2}}
)

# b) Nouvelle catégorie, avec des attributs inédits : aucune modification du schéma
db.produits.delete_one({"sku": "AV-DEMO-001"})   # permet de relancer le script
db.produits.insert_one({
    "sku": "AV-DEMO-001",
    "nom": "Antivirus Démo Premium 1 an",
    "slug": "antivirus-demo-premium-1-an",
    "prix": 39.99,
    "devise": "EUR",
    "stock": 999,
    "schema_version": 2,
    "categorie": {"nom": "Antivirus", "chemin": ["Logiciels", "Antivirus"]},
    "marque": {"_id": "M_DEMO", "nom": "Démo"},
    "specs": [
        {"k": "nb_appareils", "v": 5},
        {"k": "duree_licence", "v": 12, "u": "mois"},
        {"k": "plateformes", "v": ["Windows", "macOS", "Android"]}
    ],
    "stats_avis": {"nb": 0, "somme": 0, "moyenne": None},
    "avis_recents": [],
    "compatibles": []
})

afficher("R6 - Évolution sans migration", {
    "attribut_ajoute": db.produits.find_one({"_id": ref["_id"]}, {"_id": 0, "nom": 1, "schema_version": 1, "specs": 1}),
    "nouvelle_categorie": db.produits.find_one({"sku": "AV-DEMO-001"}, {"_id": 0, "nom": 1, "categorie": 1, "specs": 1}),
})

# R7 — Publier un avis (subset pattern + computed pattern)
avant = db.produits.find_one({"_id": ref["_id"]}, {"_id": 0, "stats_avis": 1})

nouvel_avis = {
    "produit_id": ref["_id"],
    "sku": ref["sku"],
    "client": "client_99999",
    "note": 5,
    "titre": "Parfait pour le jeu",
    "texte": "Gros gain de FPS par rapport à mon ancien processeur.",
    "date": datetime.now(timezone.utc),
    "genere": True,
}

# 1. Historique complet
db.avis.insert_one(dict(nouvel_avis))

# 2. Mise à jour de la fiche : compteurs + 5 derniers avis
db.produits.update_one(
    {"_id": ref["_id"]},
    {
        "$inc": {"stats_avis.nb": 1, "stats_avis.somme": nouvel_avis["note"]},
        "$push": {"avis_recents": {
            "$each": [{k: nouvel_avis[k] for k in ("client", "note", "titre", "date")}],
            "$position": 0,   # en tête de liste
            "$slice": 5       # on ne garde que les 5 plus récents
        }}
    }
)

# 3. Recalcul de la moyenne à partir des compteurs (pas de relecture des avis)
db.produits.update_one(
    {"_id": ref["_id"]},
    [{"$set": {"stats_avis.moyenne": {"$round": [{"$divide": ["$stats_avis.somme", "$stats_avis.nb"]}, 2]}}}]
)

afficher("R7 - Publier un avis", {
    "avant": avant["stats_avis"],
    "apres": db.produits.find_one({"_id": ref["_id"]}, {"_id": 0, "stats_avis": 1, "avis_recents": 1}),
})

# R8 — Page « tous les avis » d'un produit (references, paginée)
afficher("R8 - Tous les avis, page 1", list(db.avis.find(
    {"produit_id": ref["_id"]},
    {"_id": 0, "client": 1, "note": 1, "titre": 1, "date": 1}
).sort("date", -1).limit(10)))

# R9 — Statistiques par catégorie
afficher("R9 - Statistiques par catégorie", list(db.produits.aggregate([
    {"$group": {
        "_id": "$categorie.nom",
        "nb_produits": {"$sum": 1},
        "prix_moyen": {"$avg": "$prix"},
        "prix_min": {"$min": "$prix"},
        "prix_max": {"$max": "$prix"},
        "stock_total": {"$sum": "$stock"}
    }},
    {"$project": {
        "_id": 0, "categorie": "$_id", "nb_produits": 1, "stock_total": 1,
        "prix_moyen": {"$round": ["$prix_moyen", 2]}, "prix_min": 1, "prix_max": 1
    }},
    {"$sort": {"nb_produits": -1}}
])))

# R10 — Marques les mieux notées (computed pattern : sans lire la collection avis)
afficher("R10 - Marques les mieux notées", list(db.produits.aggregate([
    {"$match": {"stats_avis.nb": {"$gt": 0}}},
    {"$group": {
        "_id": "$marque.nom",
        "nb_avis": {"$sum": "$stats_avis.nb"},
        "somme_notes": {"$sum": "$stats_avis.somme"}
    }},
    {"$match": {"nb_avis": {"$gte": 100}}},   # marques avec assez d'avis
    {"$project": {
        "_id": 0, "marque": "$_id", "nb_avis": 1,
        "note_moyenne": {"$round": [{"$divide": ["$somme_notes", "$nb_avis"]}, 2]}
    }},
    {"$sort": {"note_moyenne": -1}},
    {"$limit": 5}
])))

# R11 — Fiche + marque détaillée + 3 derniers avis complets ($lookup)
afficher("R11 - Fiche enrichie ($lookup)", list(db.produits.aggregate([
    {"$match": {"_id": ref["_id"]}},
    {"$lookup": {"from": "marques", "localField": "marque._id", "foreignField": "_id", "as": "marque_detail"}},
    {"$lookup": {
        "from": "avis",
        "let": {"pid": "$_id"},
        "pipeline": [
            {"$match": {"$expr": {"$eq": ["$produit_id", "$$pid"]}}},
            {"$sort": {"date": -1}},
            {"$limit": 3},
            {"$project": {"_id": 0, "client": 1, "note": 1, "titre": 1, "texte": 1}}
        ],
        "as": "avis_complets"
    }},
    {"$project": {"_id": 0, "nom": 1, "prix": 1, "marque_detail": 1, "avis_complets": 1}}
])))