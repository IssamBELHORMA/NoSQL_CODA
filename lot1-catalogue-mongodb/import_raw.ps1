# Lot 1 — Import des données brutes PCPartPicker dans MongoDB
# Usage (depuis la racine du dépôt) :
#   powershell -ExecutionPolicy Bypass -File lot1-catalogue-mongodb/import_raw.ps1

$conteneur = "ldlc-mongo"
$base      = "ldlc"
$fichiers  = "cpu", "motherboard", "memory", "video-card", "case", "power-supply",
             "keyboard", "mouse", "monitor", "headphones", "os"

# 1. Copier les fichiers bruts dans le conteneur
docker cp lot1-catalogue-mongodb/raw "${conteneur}:/tmp/raw"

# 2. Importer chaque fichier dans une collection raw_<categorie>
foreach ($f in $fichiers) {
    $collection = "raw_" + ($f -replace "-", "_")   # video-card -> raw_video_card
    Write-Host "Import de $f.json -> $collection"
    docker exec $conteneur mongoimport --db $base --collection $collection `
        --file "/tmp/raw/$f.json" --jsonArray --drop --quiet
}

Write-Host "Import termine."