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

## 4. Achats croisés (`achats.py`)

**Nœud :** `Client {id}`

| Relation | Propriété | Origine |
|---|---|---|
| `(Client)-[:A_ACHETE]->(Produit)` | `nb` | Commandes Cassandra (Lot 3) |
| `(Produit)-[:ACHETE_AVEC]-(Produit)` | `nb` = nombre de commandes communes | Calculée par le batch |

Le script relit les commandes dans Cassandra (batch nocturne, voir `docs/architecture.md`) et
reconstruit ces relations. `ACHETE_AVEC` est un **pré-calcul** : la requête « achetés ensemble »
lit directement une relation au lieu de parcourir tous les clients.

## 5. Requêtes types (`requetes.py`)

| # | Cas d'usage | Parcours |
|---|---|---|
| R1 | Cartes mères achetées avec ce processeur | `ACHETE_AVEC` (pré-calculé) |
| R2 | Ce qu'ont acheté les clients de ce processeur | `Produit <- Client -> Produit` |
| R3 | Cartes mères compatibles avec ce processeur | `Produit -> Socket <- Produit` |
| R4 | Produits compatibles avec ce boîtier | `Boîtier -> Format <- Carte mère -> Socket <- Processeur` (4 sauts) |
| R5 | Produits similaires | Même catégorie, même marque, prix à ±20 % |
| R6 | Recommandations pour un client | Achats du client → `ACHETE_AVEC` → produits pas encore achetés |

```cypher
// R1 : « les clients qui ont acheté ce processeur ont aussi acheté cette carte mère »
MATCH (cpu:Produit {nom: 'AMD Ryzen 7 7800X3D'})-[r:ACHETE_AVEC]-(mb:Produit)
      -[:DANS]->(:Categorie {nom: 'Cartes mères'})
RETURN mb.nom, r.nb ORDER BY r.nb DESC LIMIT 5

// R4 : « produits compatibles avec ce boîtier »
MATCH (b:Produit {nom: 'Cooler Master TD300 Mesh'})-[:ACCEPTE]->(:Format)<-[:FORMAT]-(mb:Produit)
      -[:SOCKET]->(:Socket {nom: 'AM5'})<-[:SOCKET]-(cpu:Produit)
RETURN DISTINCT cpu.nom, cpu.prix ORDER BY cpu.prix DESC LIMIT 5
```

## 6. Compromis

| Compromis | Conséquence acceptée |
|---|---|
| Graphe alimenté **par batch** | Les recommandations ont jusqu'à un jour de retard : sans impact pour l'utilisateur |
| Produits **dupliqués** depuis MongoDB | Seuls `sku`, `nom`, `prix` sont copiés ; la fiche complète reste dans MongoDB |
| `ACHETE_AVEC` **pré-calculé** | Plus de relations à stocker, mais une lecture directe au lieu d'un parcours de tous les clients |
| Socket des CPU **déduit** de la microarchitecture | Le dataset ne le fournit pas ; quelques cas particuliers (HEDT, serveurs) ne sont pas couverts |
| Neo4j se scale surtout **verticalement** | Le graphe (produits + relations) reste petit comparé aux logs : une seule machine suffit |
