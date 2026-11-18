## 2. Sessions

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