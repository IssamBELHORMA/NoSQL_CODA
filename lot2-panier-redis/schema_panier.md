## 2. Sessions

**Scripts :**

| Script | Rôle |
|---|---|
| `client_redis.py` | Connexion partagée par les scripts ; lancé seul, il teste la connexion et mesure la latence |
| `sessions.py` | Création, lecture (TTL glissant), suppression des sessions ; démonstration du partage entre serveurs et de l'expiration |
| `panier.py` | Ajout, retrait, fusion à la connexion, expiration et validation du panier ; prix lus dans MongoDB |

```bash
python lot2-panier-redis/client_redis.py
python lot2-panier-redis/sessions.py
```

**Clé :** `session:{session_id}` (identifiant aléatoire UUID, stocké dans le cookie du navigateur)
**Structure :** Hash
**TTL :** 30 minutes, **glissant** (remis à 30 minutes à chaque requête de l'utilisateur)

| Champ | Exemple |
|---|---|
| `user_id` | `U1024` (vide pour un visiteur non connecté) |
| `nom` | `Alice` |
| `derniere_page` | `/produit/amd-ryzen-7-7800x3d` |
| `cree_le` / `maj_le` | horodatages |

**Index secondaire :** `user:{user_id}:sessions` (Set) liste les sessions d'un utilisateur,
pour le déconnecter de tous ses appareils en une opération.

| Choix | Justification |
|---|---|
| **Hash** plutôt qu'une chaîne JSON | On modifie un champ (`derniere_page`) sans relire ni réécrire toute la session |
| **TTL glissant** | La session n'expire qu'après 30 minutes d'**inactivité** ; Redis la supprime seul |
| **Écriture en transaction** (`MULTI` / `EXEC`) | Création du Hash et pose du TTL atomiques : jamais de session sans expiration |
| **Redis central** | Les serveurs web sont sans état : la session créée par le serveur A est lue par le serveur B |

## 3. Panier

| Élément | Choix | Justification |
|---|---|---|
| Clé | `panier:{id}` : `user_id` si connecté, `session_id` sinon | Un visiteur anonyme peut remplir un panier |
| Structure | **Hash** `{ sku: quantité }` | `HINCRBY` modifie une quantité de façon atomique, sans relire le panier |
| TTL | **24 heures, glissant** | Panier abandonné supprimé automatiquement ; prolongé à chaque action |
| Prix | **Non stockés** dans Redis, lus dans MongoDB à l'affichage | Le catalogue reste la source de vérité : un changement de prix est visible tout de suite |
| Connexion | **Fusion** du panier anonyme dans celui du compte (transaction) | Le client ne perd pas ses articles en se connectant |
| Commande | Total calculé, puis panier supprimé | L'historique des commandes est stocké dans Cassandra (Lot 3) |

## 4. Persistance et mémoire

| Paramètre | Choix | Justification |
|---|---|---|
| Persistance | **AOF** (`appendonly yes`) | Chaque écriture est journalisée sur disque : un redémarrage ne vide pas les paniers |
| Synchronisation | `appendfsync everysec` | Au plus **1 seconde** d'écritures perdue en cas de panne, sans ralentir chaque écriture |
| Mémoire | `maxmemory 256mb` | Redis travaille en RAM : on borne sa consommation |
| Éviction | `volatile-lru` | Si la mémoire est pleine, Redis supprime en priorité les clés **avec TTL** les moins utilisées récemment (vieux paniers, sessions inactives) |

**Compromis :** perdre au plus une seconde de modifications de panier est acceptable pour un
site e-commerce. Ce choix est cohérent avec le positionnement **AP** : la rapidité et la
disponibilité priment sur la durabilité absolue. Les données critiques (commandes) ne sont
pas dans Redis mais dans Cassandra.