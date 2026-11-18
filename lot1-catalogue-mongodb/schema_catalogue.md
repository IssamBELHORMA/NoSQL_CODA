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