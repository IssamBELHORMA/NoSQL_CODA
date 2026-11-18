# Lot 1 — Catalogue Produits (MongoDB)

## 1. Choix technologique : MongoDB (base orientée document)

| Besoin LDLC | Réponse MongoDB |
|---|---|
| Schémas variables selon la catégorie (CPU, clavier, logiciel…) | Les documents d'une même collection n'ont pas besoin d'avoir les mêmes champs |
| Évolution sans migration (nouveaux attributs, nouvelles catégories) | Pas de `ALTER TABLE` : on ajoute le champ dans les nouveaux documents |
| Fiches lues très souvent, écrites rarement | Une fiche complète = **1 seul document** → 1 lecture, aucune jointure |
| Sous-documents (specs, avis, produits compatibles) | Documents imbriqués et tableaux natifs |
| 27 000 références, millions de visites | Index secondaires, réplication (replica set), sharding possible |

**Pourquoi pas un SGBDR ?** Il faudrait soit une table avec des centaines de colonnes vides,
soit un modèle EAV (Entité-Attribut-Valeur) coûteux en jointures, et une migration à chaque
nouvelle catégorie de produits.

**Positionnement CAP :** MongoDB en replica set est **CP** : par défaut, les écritures et
les lectures passent par le nœud primaire. Pour un catalogue, afficher un prix faux est
plus grave qu'une courte indisponibilité en écriture. Les lectures peuvent être déportées
sur les secondaires (`readPreference: secondaryPreferred`) pour absorber les pics de
trafic (sorties de composants), en acceptant un léger retard de réplication.

## 2. Collections et validation

| Collection | Volume | Rôle |
|---|---|---|
| `produits` | plusieurs dizaines de milliers (27 000 chez LDLC) | Fiches produits, document principal lu par le site |
| `marques` | plusieurs centaines (600 chez LDLC) | Référentiel des marques, extrait automatiquement des fiches |
| `avis` | plusieurs centaines de milliers | Historique complet des avis clients |
| `raw_<categorie>` | 1 par fichier source | Données brutes importées, avant transformation |

**Validation souple :** la collection `produits` utilise un validateur `$jsonSchema` qui impose
les **champs communs** à toutes les fiches (`sku`, `nom`, `prix`, `stock`, `categorie`) avec
leur type, mais **autorise tous les champs supplémentaires**. On garde la flexibilité du
modèle document (un processeur et un clavier n'ont pas les mêmes attributs), sans accepter
de fiches incomplètes ou mal typées (un prix négatif ou en texte, par exemple).

## 3. Source des données et import

**Source :** [pc-part-dataset](https://github.com/docyx/pc-part-dataset), jeu de données
de composants récupérés sur PCPartPicker (mars 2024). Les fichiers JSON bruts sont
versionnés dans `raw/` pour que le projet soit reproductible sans téléchargement.

**Catégories retenues (11)**, couvrant les trois familles de l'énoncé :

| Famille | Fichiers |
|---|---|
| Composants | `cpu`, `motherboard`, `memory`, `video-card`, `case`, `power-supply` |
| Périphériques | `keyboard`, `mouse`, `monitor`, `headphones` |
| Logiciels | `os` |

**Le schéma variable en pratique** : chaque fichier a ses propres attributs.

| Catégorie | Attributs spécifiques |
|---|---|
| Processeur | `core_count`, `core_clock`, `boost_clock`, `microarchitecture`, `tdp`, `graphics` |
| Clavier | `style`, `switches`, `backlit`, `tenkeyless`, `connection_type`, `color` |

**Pipeline d'import en deux temps :**
1. **Import brut** : chaque fichier est chargé tel quel dans une collection `raw_<categorie>`
   (`mongoimport`).
2. **Transformation** : un pipeline d'agrégation convertit les données brutes vers le modèle
   `produits` (catégorie, marque, specs au format Attribute pattern…) et les écrit avec `$merge`.

**Limites du dataset et enrichissement :**
- pas de marque : elle est extraite du nom du produit ;
- prix en dollars : convertis en euros avec un taux fixe (hypothèse documentée) ;
- pas de stock, de SKU ni d'avis : générés lors de la transformation.


## 4. Modèle du document produit

Les données brutes sont transformées par un pipeline d'agrégation (`data.mongodb.js`),
puis écrites dans `produits` avec `$merge`. Le validateur `$jsonSchema` s'applique aussi
à ces écritures.

### Correspondance données brutes → modèle

| Champ `produits` | Origine | Traitement |
|---|---|---|
| `sku` | généré | préfixe de catégorie + fin de l'identifiant brut (`CPU-0A1B2C3D4E`) |
| `nom` | `name` | repris tel quel |
| `slug` | `name` | minuscules, espaces → tirets (URL de la fiche) |
| `prix` | `price` | converti en euros (taux fixe 0,92, hypothèse) ; produits sans prix exclus |
| `stock` | généré | entier aléatoire entre 0 et 199 |
| `categorie` | fichier source | `{ nom, chemin }`, ex. `Composants > Processeurs` |
| `marque` | `name` | premier mot du nom (ou deux mots pour « Fractal Design », « be quiet! »…) |
| `specs` | tous les autres champs | convertis en paires `{ k, v }`, valeurs `null` supprimées |
| `source` | — | traçabilité vers la collection et le document brut |

### Patterns appliqués

1. **Polymorphic pattern** : une seule collection `produits` pour toutes les catégories.
   Les champs communs sont identiques partout ; ce qui varie est regroupé dans `specs`.
2. **Attribute pattern** : les attributs spécifiques sont stockés sous forme de paires
   `{ k, v }`. Ils sont générés automatiquement avec `$objectToArray` : une nouvelle
   catégorie ou un nouvel attribut ne demande **aucune modification du code ni du schéma**.
   Un seul index `{ "specs.k": 1, "specs.v": 1 }` suffit pour filtrer sur n'importe quel
   attribut de n'importe quelle catégorie.
3. **Extended reference** : `marque: { _id, nom }`. Le nom est embarqué pour l'affichage
   sans jointure ; la collection `marques` (générée à partir des produits) garde le
   référentiel complet.
4. **Schema versioning** : `schema_version: 1` permet de faire évoluer le modèle et de
   migrer les fiches progressivement, sans interruption de service.

### Exemple de document

```json
{
  "_id": ObjectId("..."),
  "sku": "CPU-0A1B2C3D4E",
  "nom": "AMD Ryzen 7 9800X3D",
  "slug": "amd-ryzen-7-9800x3d-0a1b2c3d4e",
  "prix": 415.38,
  "devise": "EUR",
  "stock": 87,
  "schema_version": 1,
  "categorie": { "nom": "Processeurs", "chemin": ["Composants", "Processeurs"] },
  "marque": { "_id": "M_AMD", "nom": "AMD" },
  "specs": [
    { "k": "core_count", "v": 8 },
    { "k": "core_clock", "v": 4.7 },
    { "k": "boost_clock", "v": 5.2 },
    { "k": "microarchitecture", "v": "Zen 5" },
    { "k": "tdp", "v": 120 },
    { "k": "graphics", "v": "Radeon" }
  ],
  "stats_avis": { "nb": 0, "somme": 0, "moyenne": null },
  "avis_recents": [],
  "compatibles": [],
  "source": { "dataset": "pc-part-dataset", "raw_collection": "raw_cpu", "raw_id": ObjectId("...") }
}
```

**Résultat de la transformation :** 51 837 documents bruts → **11 012 produits** (les fiches
sans prix, soit environ 80 % du dataset, sont exclues) et **252 marques** extraites
automatiquement.

## 5. Avis clients : Subset pattern et Computed pattern

Les avis posent un dilemme **Embedded vs References** :
- les embarquer tous dans la fiche rend l'affichage immédiat, mais le document grossit
  sans limite (plafond de 16 Mo par document) et chaque nouvel avis réécrit la fiche
  la plus lue du site ;
- les mettre uniquement dans une collection séparée oblige à une seconde requête
  à chaque affichage de fiche.

**Solution hybride :**

| Où | Quoi | Pattern |
|---|---|---|
| Collection `avis` | l'historique **complet** des avis (1 document par avis) | References (`produit_id`) |
| `produits.avis_recents` | les **5 derniers** avis, résumés | **Subset pattern** |
| `produits.stats_avis` | `{ nb, somme, moyenne }` | **Computed pattern** |

- La fiche produit s'affiche en **une seule lecture** : note moyenne, nombre d'avis et
  5 derniers avis.
- La page « tous les avis » interroge la collection `avis`, paginée (`skip` / `limit`).
- La moyenne n'est pas recalculée à chaque affichage : `somme` et `nb` sont mis à jour à
  chaque nouvel avis, et `moyenne = somme / nb`.

**Exemple de document `avis` :**
```json
{
  "_id": ObjectId("..."),
  "produit_id": ObjectId("..."),
  "sku": "CPU-25B6C03A79",
  "client": "client_04521",
  "note": 5,
  "titre": "Excellent produit",
  "texte": "Conforme à la description, je recommande.",
  "date": ISODate("2026-03-14T10:22:00Z"),
  "genere": true
}
```

**Données de test :** le dataset source ne contient pas d'avis. Ils sont **générés**
aléatoirement (pseudos `client_XXXXX`, champ `genere: true`) pour 3 000 produits,
avec 1 à 15 avis chacun et une répartition des notes réaliste (majorité de 4 et 5).