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
