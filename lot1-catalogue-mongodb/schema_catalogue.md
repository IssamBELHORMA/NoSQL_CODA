# Lot 1 — Catalogue Produits (MongoDB)

## 1. Choix technologique : MongoDB (document)

| Besoin LDLC | Pourquoi MongoDB |
|---|---|
| Schémas différents selon la catégorie | Les documents d'une même collection n'ont pas besoin des mêmes champs |
| Évolution sans migration | Pas de `ALTER TABLE` : un nouveau champ s'ajoute simplement aux documents |
| Fiches lues très souvent | Une fiche = 1 document = 1 lecture, sans jointure |
| Sous-documents (specs, avis, compatibilités) | Documents imbriqués et tableaux natifs |

Un SGBDR imposerait des centaines de colonnes vides ou un modèle EAV coûteux en jointures.

**CAP : CP.** En replica set, lectures et écritures passent par le primaire : un prix faux est
plus grave qu'une courte indisponibilité. Pendant les pics de trafic, les lectures peuvent
être déportées sur les secondaires.

## 2. Données et scripts

**Source :** [pc-part-dataset](https://github.com/docyx/pc-part-dataset) (données PCPartPicker,
mars 2024), 11 catégories couvrant composants, périphériques et logiciels. Les fichiers bruts
sont versionnés dans `raw/`.

| Script | Rôle |
|---|---|
| `import_raw.py` | Charge les fichiers JSON bruts dans des collections `raw_<categorie>` |
| `data.py` | Construit la base : validation, transformation vers `produits`, marques, avis de test, index |
| `requetes.py` | Requêtes types du site (R1 à R11) |


**Étapes de `data.py` :**
1. Supprime `produits`, `marques` et `avis` (relançable ; les collections `raw_*` sont conservées).
2. Crée `produits` avec le validateur `$jsonSchema`.
3. Transforme chaque catégorie brute (filtre des produits sans prix, marque, prix en euros,
   SKU, stock, `specs`) et l'écrit dans `produits` avec `$merge`.
4. Génère le référentiel `marques` à partir des produits (`$out`).
5. Génère les avis de test, puis met à jour les fiches (5 derniers avis, moyenne).
6. Crée les index.
7. Affiche un bilan et vérifie avec `explain()` que les requêtes utilisent les index.

```bash
pip install -r requirements.txt
python lot1-catalogue-mongodb/import_raw.py
python lot1-catalogue-mongodb/data.py
python lot1-catalogue-mongodb/requetes.py
```

**Résultat :** 51 837 documents bruts → **11 012 produits** (fiches sans prix exclues),
**252 marques**, environ **24 000 avis**.

**Enrichissements** (absents du dataset) : marque extraite du nom, prix convertis en euros
(taux fixe 0,92), stock, SKU et avis générés (marqués `genere: true`).

## 3. Modèle de données

| Collection | Rôle |
|---|---|
| `produits` | Fiches produits, toutes catégories confondues |
| `marques` | Référentiel des marques, généré à partir des produits |
| `avis` | Historique complet des avis |

**Exemple de produit :**
```json
{
  "sku": "CPU-25B6C03A79",
  "nom": "AMD Ryzen 7 7800X3D",
  "prix": 312.85,
  "stock": 105,
  "schema_version": 1,
  "categorie": { "nom": "Processeurs", "chemin": ["Composants", "Processeurs"] },
  "marque": { "_id": "M_AMD", "nom": "AMD" },
  "specs": [
    { "k": "core_count", "v": 8 },
    { "k": "microarchitecture", "v": "Zen 4" },
    { "k": "tdp", "v": 120 }
  ],
  "stats_avis": { "nb": 12, "somme": 47, "moyenne": 3.92 },
  "avis_recents": [ { "client": "client_47214", "note": 5, "titre": "Parfait" } ],
  "compatibles": []
}
```

## 4. Choix de modélisation

| Choix | Justification |
|---|---|
| **Une seule collection `produits`** (Polymorphic pattern) | Champs communs partout, champs spécifiques regroupés dans `specs` |
| **`specs: [{k, v}]`** (Attribute pattern) | Un seul index pour filtrer sur n'importe quel attribut de n'importe quelle catégorie ; une nouvelle catégorie ne demande aucune modification |
| **Marque copiée dans le produit** (Extended reference) | Affichage et filtre par marque sans jointure ; le détail reste dans `marques` |
| **5 derniers avis dans la fiche** (Subset pattern) | Fiche affichée en une lecture, sans faire grossir le document sans limite (plafond de 16 Mo) |
| **Historique des avis dans `avis`** (References) | Croissance illimitée, page « tous les avis » paginée |
| **Moyenne pré-calculée** (Computed pattern) | Note affichée et triable sans relire tous les avis |
| **Validation `$jsonSchema` souple** | Champs communs obligatoires et typés, champs spécifiques libres |
| **`schema_version`** (Schema versioning) | Faire évoluer le modèle et migrer les fiches progressivement |

**Compromis accepté :** quelques données dupliquées (nom de marque, résumé des avis) et une
double écriture à chaque avis, en échange de lectures rapides. C'est adapté à un catalogue
lu beaucoup plus souvent qu'il n'est modifié.

## 5. Index

| Index | Requête servie |
|---|---|
| `sku` unique, `slug` unique | Accès direct à une fiche |
| `categorie.chemin + prix` | Liste d'une catégorie triée par prix |
| `specs.k + specs.v` | Filtres techniques |
| `marque.nom + prix` | Filtre par marque et budget |
| texte sur `nom` | Barre de recherche |
| `avis : produit_id + date` | Avis d'un produit, plus récents d'abord |

**Vérification avec `explain()` :** toutes les requêtes utilisent un index (`IXSCAN` ou
`TEXT_MATCH`), sans aucun `COLLSCAN`. Exemple : lister 20 processeurs examine 20 documents
au lieu de 11 012.

## 6. Requêtes types (`requetes.py`)

| # | Usage | Ce qu'elle montre |
|---|---|---|
| R1 | Fiche produit | Fiche complète en une lecture |
| R2 | Catégorie paginée, triée par prix | Index composé + `skip` / `limit` |
| R3 | Filtres techniques (CPU Zen 4, clavier sans fil RGB) | Attribute pattern : même index pour deux catégories |
| R4 | Recherche texte | Tri par pertinence |
| R5 | Marque + budget | Extended reference |
| R6 | Nouvel attribut, nouvelle catégorie | Aucune migration |
| R7 | Publier un avis | Subset + Computed pattern |
| R8 | Tous les avis d'un produit | References paginées |
| R9, R10 | Statistiques par catégorie, marques les mieux notées | Agrégations |
| R11 | Fiche + marque + avis complets | `$lookup`, pour les besoins ponctuels |