-- =====================================================================
-- Lot 3 — Logs et Analytics (Cassandra) : keyspace et tables
-- Une table par requête (query-driven design)
-- =====================================================================

-- En local : un seul nœud (RF 1). En production : RF 3.
CREATE KEYSPACE IF NOT EXISTS ldlc_logs
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE ldlc_logs;

-- Journal brut des événements (pages vues, clics, recherches)
-- Partition (jour, bucket) : une journée est répartie sur 10 partitions
CREATE TABLE IF NOT EXISTS evenements_par_jour (
    jour        date,
    bucket      int,
    ts          timeuuid,
    type        text,
    user_id     text,
    session_id  text,
    sku         text,
    recherche   text,
    PRIMARY KEY ((jour, bucket), ts)
) WITH CLUSTERING ORDER BY (ts DESC)
  AND default_time_to_live = 34128000;   -- 395 jours

-- « Combien de vues pour ce produit aujourd'hui ? »
CREATE TABLE IF NOT EXISTS vues_par_produit (
    sku   text,
    jour  date,
    vues  counter,
    PRIMARY KEY ((sku), jour)
) WITH CLUSTERING ORDER BY (jour DESC);

-- « Top produits consultés cette semaine » : 7 partitions lues, tri côté application
CREATE TABLE IF NOT EXISTS vues_par_jour (
    jour  date,
    sku   text,
    vues  counter,
    PRIMARY KEY ((jour), sku)
);

-- « Historique des commandes d'un client » (plus récentes d'abord, sans TTL)
CREATE TABLE IF NOT EXISTS commandes_par_client (
    user_id       text,
    date_commande timestamp,
    commande_id   uuid,
    total         decimal,
    lignes        map<text, int>,      -- sku -> quantité
    PRIMARY KEY ((user_id), date_commande, commande_id)
) WITH CLUSTERING ORDER BY (date_commande DESC, commande_id ASC);
