# Architecture globale — Refonte LDLC

## Schéma

```mermaid
flowchart TB
    U["👤 Clients<br/>(web / mobile)"] --> LB["Load Balancer"]
    LB --> W1["Serveur web 1"]
    LB --> W2["Serveur web 2"]
    LB --> W3["Serveur web n"]

    subgraph API["Couche services (API)"]
        S1["Service Catalogue"]
        S2["Service Panier / Session"]
        S3["Service Tracking & Commandes"]
        S4["Service Recommandations"]
    end

    W1 & W2 & W3 --> API

    subgraph DATA["Couche données — persistance polyglotte"]
        M[("MongoDB<br/>Lot 1 : Catalogue produits<br/>Document")]
        R[("Redis<br/>Lot 2 : Paniers & Sessions<br/>Clé-valeur")]
        C[("Cassandra<br/>Lot 3 : Logs & Analytics<br/>Colonnes")]
        N[("Neo4j<br/>Lot 4 : Recommandations<br/>Graphe")]
    end

    S1 -->|lecture / écriture fiches| M
    S2 -->|lecture / écriture < 1 ms, TTL| R
    S3 -->|écriture massive d'événements| C
    S4 -->|parcours de relations| N

    M -.->|synchro produits<br/>batch| N
    C -.->|historique d'achats<br/>batch nocturne| N
```

## Rôle de chaque base

| Lot | Base | Famille | Pourquoi | Priorité CAP |
|---|---|---|---|---|
| 1. Catalogue | MongoDB | Document | Schémas variables par catégorie, sous-documents (specs, avis), lectures fréquentes | CP (replica set : lectures cohérentes sur le primaire) |
| 2. Panier & Sessions | Redis | Clé-valeur | Latence sub-milliseconde, TTL natif, sessions partagées entre serveurs web | AP (perte d'un panier tolérable, disponibilité prioritaire) |
| 3. Logs & Analytics | Cassandra | Colonnes | Millions d'écritures/jour, données temporelles, rétention longue | AP (cohérence à terme acceptable pour des logs) |
| 4. Recommandations | Neo4j | Graphe | Parcours de relations (achats croisés, compatibilités) | CP |

## Flux de données
- **Temps réel** : chaque service lit et écrit directement dans sa base (traits pleins).
- **Batch** (pointillés) : Neo4j est alimenté périodiquement à partir des produits (MongoDB) et de l'historique d'achats (Cassandra), pour calculer les relations « achetés ensemble ». Les recommandations n'ont pas besoin d'être à jour à la seconde près.
- **Sessions partagées** : les serveurs web sont *stateless*. La session est stockée dans Redis, donc n'importe quel serveur peut traiter la requête suivante d'un client.