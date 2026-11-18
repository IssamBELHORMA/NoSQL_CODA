# =====================================================================
# Lot 1 — Import des données brutes PCPartPicker dans MongoDB
# Usage (depuis la racine du dépôt) :
#   python lot1-catalogue-mongodb/import_raw.py
# =====================================================================

import json
import sys
from pathlib import Path

from pymongo import MongoClient

sys.stdout.reconfigure(encoding="utf-8")

URI = "mongodb://localhost:27017"
BASE = "ldlc"
DOSSIER_RAW = Path(__file__).parent / "raw"
FICHIERS = ["cpu", "motherboard", "memory", "video-card", "case", "power-supply",
            "keyboard", "mouse", "monitor", "headphones", "os"]

db = MongoClient(URI)[BASE]

for f in FICHIERS:
    nom_collection = "raw_" + f.replace("-", "_")   # video-card -> raw_video_card
    collection = db[nom_collection]
    collection.drop()                                # relançable sans doublons

    with open(DOSSIER_RAW / f"{f}.json", encoding="utf-8") as fichier:
        documents = json.load(fichier)

    collection.insert_many(documents)
    print(f"{f}.json -> {nom_collection} : {collection.count_documents({})} documents")

print("Import termine.")