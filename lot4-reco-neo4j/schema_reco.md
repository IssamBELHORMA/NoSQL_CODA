# Lot 4 — Recommandations produits (Neo4j)

## 1. Choix technologique : Neo4j (graphe)

| Besoin LDLC | Pourquoi Neo4j |
|---|---|
| Relations complexes (compatibilité, gamme, marque) | Les relations sont stockées comme des données, avec leurs propriétés |
| Parcours sur plusieurs niveaux | Chaque saut suit un pointeur (*index-free adjacency*) au lieu d'une jointure |
| « Les clients qui ont acheté X ont aussi acheté Y » | Requête naturelle en Cypher : `(x)<-[:A_ACHETE]-(client)-[:A_ACHETE]->(y)` |

En SQL, un parcours à 4 niveaux demande 4 jointures sur des tables de plusieurs millions de
lignes ; dans un graphe, le coût dépend seulement du nombre de voisins parcourus.

**CAP : CP.** Un cluster Neo4j accepte les écritures sur un seul leader (consensus Raft).
Le graphe est reconstruit par batch : une courte indisponibilité de l'écriture est sans conséquence.

## 2. Modèle

**Nœuds :** `Produit {sku, nom, prix}`, `Marque {nom}`, `Categorie {nom}`

**Relations :** `(Produit)-[:DE_MARQUE]->(Marque)`, `(Produit)-[:DANS]->(Categorie)`

```bash
python lot4-reco-neo4j/import_graphe.py
```

Les produits sont copiés depuis MongoDB (Lot 1), avec seulement les champs utiles aux
recommandations : MongoDB reste la source de vérité de la fiche produit. Des contraintes
d'unicité (`sku`, `nom`) évitent les doublons et créent les index utilisés par `MERGE`.

## 3. Compatibilités (`compatibilites.py`)

**Nœuds :** `Socket {nom}`, `Format {nom}`

| Relation | Signification |
|---|---|
| `(Processeur)-[:SOCKET]->(Socket)` | Socket du processeur (déduit de la microarchitecture : Zen 4 → AM5...) |
| `(Carte mère)-[:SOCKET]->(Socket)` | Socket de la carte mère |
| `(Carte mère)-[:FORMAT]->(Format)` | ATX, Micro ATX, Mini ITX... |
| `(Boîtier)-[:ACCEPTE]->(Format)` | Formats de carte mère acceptés par le boîtier |

**Choix :** la compatibilité passe par des nœuds intermédiaires (`Socket`, `Format`) plutôt que par
une relation `COMPATIBLE_AVEC` entre chaque paire de produits. Avec 223 cartes mères AM5 et 30
processeurs AM5, il faudrait 6 690 relations ; ici, 253 suffisent, et un nouveau produit n'a
besoin que d'une relation vers son socket.
