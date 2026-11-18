# Lot 3 — Logs et Analytics (Cassandra)

## 1. Choix technologique : Cassandra (colonnes)

| Besoin LDLC | Pourquoi Cassandra |
|---|---|
| Des millions d'événements par jour | Écritures en append (commit log + memtable), très rapides |
| Chaque clic = une écriture | Pas de lecture avant écriture, débit qui augmente en ajoutant des nœuds |
| Requêtes connues à l'avance | Modélisation *query-driven* : une table par requête |
| Conservation sur plusieurs mois | TTL natif, données réparties sur le cluster |

**CAP : AP.** Pas de nœud maître : si un nœud tombe, les autres continuent d'écrire.
Perdre ou recevoir en retard quelques événements de navigation n'a pas d'impact métier.

## 2. Schéma (`schema.cql`)

```bash
python lot3-logs-cassandra/client_cassandra.py
```

| Table | Partition key | Clustering | Requête servie |
|---|---|---|---|
| `evenements_par_jour` | `(jour, bucket)` | `ts DESC` | Journal brut d'une journée |
| `vues_par_produit` | `sku` | `jour DESC` | Vues d'un produit aujourd'hui |
| `vues_par_jour` | `jour` | `sku` | Top produits de la semaine |
| `commandes_par_client` | `user_id` | `date_commande DESC` | Historique des commandes d'un client |

| Choix | Justification |
|---|---|
| **Bucket** dans la partition key | Sans lui, toutes les écritures du jour iraient sur la même partition (partition chaude) |
| **`ts` en `timeuuid`** | Unique et trié par date : deux clics à la même milliseconde ne s'écrasent pas |
| **Compteurs** (`counter`) | Les vues sont incrémentées à l'écriture : la lecture est immédiate, sans `COUNT(*)` |
| **TTL de 13 mois** sur le journal brut | Les vieux logs sont supprimés automatiquement ; les compteurs et commandes sont conservés |

## 3. Données de test (`generer_logs.py`)

```bash
python lot3-logs-cassandra/generer_logs.py
```

50 000 événements sur les 7 derniers jours (70 % de vues, 20 % de clics, 10 % de recherches),
sur les SKU réels du catalogue MongoDB. La popularité suit une loi de puissance : quelques
produits concentrent beaucoup de vues. Les écritures sont envoyées en parallèle
(`execute_concurrent_with_args`) avec des requêtes préparées.

## 4. Commandes (`commandes.py`)

```bash
python lot3-logs-cassandra/commandes.py
```

`enregistrer_commande(user_id, lignes)` reçoit le contenu du panier Redis (`{sku: quantité}`),
lit les prix dans MongoDB, calcule le total et écrit la commande dans `commandes_par_client`.
Le script génère 3 000 commandes de test (configurations PC AM5) sur les 12 derniers mois.

| Choix | Justification |
|---|---|
| Partition par **client** | L'historique d'un client est lu en une seule partition, déjà trié par date |
| `lignes` en **map** `sku -> quantité` | La commande est lue en entier, jamais modifiée : pas besoin d'une table séparée |
| Prix **figés** dans le total | Le prix payé ne doit pas changer si le catalogue change ensuite |
| Écriture en **LOCAL_QUORUM** | Une commande ne doit pas être perdue : on attend la majorité des réplicas (les logs restent en `ONE`) |

## 5. Requêtes types (`requetes.py`)

| # | Question métier | Lecture |
|---|---|---|
| R1 | Top 10 des produits consultés cette semaine | 7 partitions de `vues_par_jour`, tri en Python |
| R2 | Vues d'un produit aujourd'hui (et 7 derniers jours) | 1 partition de `vues_par_produit` |
| R3 | Recherches les plus fréquentes du jour | 10 partitions (buckets) de `evenements_par_jour` |
| R4 | Historique des commandes d'un client | 1 partition de `commandes_par_client` |

```sql
-- R2 : vues d'un produit aujourd'hui
SELECT vues FROM vues_par_produit WHERE sku = 'CPU-F7926AE16E' AND jour = '2026-11-18';

-- R4 : 10 dernières commandes d'un client
SELECT date_commande, total, lignes FROM commandes_par_client WHERE user_id = 'U1024' LIMIT 10;
```

Aucune requête n'utilise `ALLOW FILTERING` : chaque requête connaît sa partition key.

## 6. Compromis

| Compromis | Conséquence acceptée |
|---|---|
| **Dénormalisation** : une vue est écrite 3 fois (journal + 2 compteurs) | Plus d'écritures, mais des écritures peu coûteuses dans Cassandra ; chaque lecture est directe |
| **Pas de tri sur les compteurs** | Le top de la semaine est calculé côté application (ou par un batch Spark en production) |
| **Compteurs** non idempotents | Si une écriture est rejouée après un timeout, une vue peut être comptée deux fois : acceptable pour des statistiques |
| **Cohérence à terme** (AP) | Un compteur peut être légèrement en retard sur un autre nœud ; aucun impact pour de l'analytics |
| **Requêtes figées** | Une nouvelle question métier demande une nouvelle table (prix de la modélisation query-driven) |

**Lien avec les autres lots :** le panier Redis (Lot 2) devient une commande dans Cassandra à la
validation ; les commandes alimentent ensuite les recommandations « achetés ensemble » (Lot 4).
