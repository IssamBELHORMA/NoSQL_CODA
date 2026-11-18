// =====================================================================
// Lot 1 — Catalogue Produits (MongoDB) : requêtes types
// Prérequis : avoir exécuté data.mongodb.js
// =====================================================================

use('ldlc');

const resultats = {};

// Produit de référence pour les exemples
const ref = db.produits.findOne({ nom: "AMD Ryzen 7 7800X3D" });

// R1 — Fiche produit complète, en une seule lecture (index slug)
resultats.R1_fiche_produit = db.produits.findOne(
  { slug: ref.slug },
  { _id: 0, source: 0 }
);

// R2 — Catégorie Processeurs, page 2 (10 par page), prix croissant
const PAGE = 2, TAILLE_PAGE = 10;
resultats.R2_categorie_page2 = db.produits.find(
  { "categorie.chemin": "Processeurs" },
  { _id: 0, nom: 1, prix: 1, "marque.nom": 1, "stats_avis.moyenne": 1 }
).sort({ prix: 1 }).skip((PAGE - 1) * TAILLE_PAGE).limit(TAILLE_PAGE).toArray();

// R3 — Filtres techniques (attribute pattern)
// Processeurs d'au moins 8 cœurs, microarchitecture Zen 4
resultats.R3a_cpu_8coeurs_zen4 = db.produits.find(
  { specs: { $all: [
      { $elemMatch: { k: "core_count", v: { $gte: 8 } } },
      { $elemMatch: { k: "microarchitecture", v: "Zen 4" } }
  ] } },
  { _id: 0, nom: 1, prix: 1 }
).sort({ prix: 1 }).limit(5).toArray();

// Claviers sans fil rétroéclairés RGB : même requête, même index, autre catégorie
resultats.R3b_claviers_sans_fil_rgb = db.produits.find(
  { specs: { $all: [
      { $elemMatch: { k: "connection_type", v: "Wireless" } },
      { $elemMatch: { k: "backlit", v: "RGB" } }
  ] } },
  { _id: 0, nom: 1, prix: 1 }
).sort({ prix: 1 }).limit(5).toArray();

// R4 — Recherche texte, triée par pertinence
resultats.R4_recherche_ryzen_7 = db.produits.find(
  { $text: { $search: "ryzen 7" } },
  { _id: 0, nom: 1, prix: 1, score: { $meta: "textScore" } }
).sort({ score: { $meta: "textScore" } }).limit(5).toArray();

// R5 — Marque + budget (extended reference : pas de jointure)
resultats.R5_corsair_moins_100 = db.produits.find(
  { "marque.nom": "Corsair", prix: { $lte: 100 } },
  { _id: 0, nom: 1, prix: 1, "categorie.nom": 1 }
).sort({ prix: -1 }).limit(5).toArray();

// R6 — Évolution sans migration
// a) Nouvel attribut sur une fiche existante (+ version de schéma)
db.produits.updateOne(
  { _id: ref._id },
  { $addToSet: { specs: { k: "pcie_version", v: "5.0" } }, $set: { schema_version: 2 } }
);

// b) Nouvelle catégorie, avec des attributs inédits : aucune modification du schéma
db.produits.deleteOne({ sku: "AV-DEMO-001" });   // permet de relancer le fichier
db.produits.insertOne({
  sku: "AV-DEMO-001",
  nom: "Antivirus Démo Premium 1 an",
  slug: "antivirus-demo-premium-1-an",
  prix: 39.99,
  devise: "EUR",
  stock: NumberInt(999),
  schema_version: 2,
  categorie: { nom: "Antivirus", chemin: ["Logiciels", "Antivirus"] },
  marque: { _id: "M_DEMO", nom: "Démo" },
  specs: [
    { k: "nb_appareils", v: 5 },
    { k: "duree_licence", v: 12, u: "mois" },
    { k: "plateformes", v: ["Windows", "macOS", "Android"] }
  ],
  stats_avis: { nb: 0, somme: 0, moyenne: null },
  avis_recents: [],
  compatibles: []
});

resultats.R6_evolution = {
  attribut_ajoute: db.produits.findOne({ _id: ref._id }, { _id: 0, nom: 1, schema_version: 1, specs: 1 }),
  nouvelle_categorie: db.produits.findOne({ sku: "AV-DEMO-001" }, { _id: 0, nom: 1, categorie: 1, specs: 1 })
};

// R7 — Publier un avis (subset pattern + computed pattern)
const avant = db.produits.findOne({ _id: ref._id }, { _id: 0, stats_avis: 1 });

const nouvelAvis = {
  produit_id: ref._id,
  sku: ref.sku,
  client: "client_99999",
  note: 5,
  titre: "Parfait pour le jeu",
  texte: "Gros gain de FPS par rapport à mon ancien processeur.",
  date: new Date(),
  genere: true
};

// 1. Historique complet
db.avis.insertOne(nouvelAvis);

// 2. Mise à jour de la fiche : compteurs + 5 derniers avis
db.produits.updateOne(
  { _id: ref._id },
  {
    $inc: { "stats_avis.nb": 1, "stats_avis.somme": nouvelAvis.note },
    $push: { avis_recents: {
      $each: [{ client: nouvelAvis.client, note: nouvelAvis.note, titre: nouvelAvis.titre, date: nouvelAvis.date }],
      $position: 0,   // en tête de liste
      $slice: 5       // on ne garde que les 5 plus récents
    } }
  }
);

// 3. Recalcul de la moyenne à partir des compteurs (pas de relecture des avis)
db.produits.updateOne(
  { _id: ref._id },
  [{ $set: { "stats_avis.moyenne": { $round: [{ $divide: ["$stats_avis.somme", "$stats_avis.nb"] }, 2] } } }]
);

resultats.R7_publier_avis = {
  avant: avant.stats_avis,
  apres: db.produits.findOne({ _id: ref._id }, { _id: 0, stats_avis: 1, avis_recents: 1 })
};

// R8 — Page « tous les avis » d'un produit (references, paginée)
resultats.R8_tous_les_avis_page1 = db.avis.find(
  { produit_id: ref._id },
  { _id: 0, client: 1, note: 1, titre: 1, date: 1 }
).sort({ date: -1 }).limit(10).toArray();

// R9 — Statistiques par catégorie
resultats.R9_stats_categories = db.produits.aggregate([
  { $group: {
      _id: "$categorie.nom",
      nb_produits: { $sum: 1 },
      prix_moyen: { $avg: "$prix" },
      prix_min: { $min: "$prix" },
      prix_max: { $max: "$prix" },
      stock_total: { $sum: "$stock" }
  } },
  { $project: {
      _id: 0, categorie: "$_id", nb_produits: 1, stock_total: 1,
      prix_moyen: { $round: ["$prix_moyen", 2] }, prix_min: 1, prix_max: 1
  } },
  { $sort: { nb_produits: -1 } }
]).toArray();

// R10 — Marques les mieux notées (computed pattern : sans lire la collection avis)
resultats.R10_top_marques_notes = db.produits.aggregate([
  { $match: { "stats_avis.nb": { $gt: 0 } } },
  { $group: {
      _id: "$marque.nom",
      nb_avis: { $sum: "$stats_avis.nb" },
      somme_notes: { $sum: "$stats_avis.somme" }
  } },
  { $match: { nb_avis: { $gte: 100 } } },   // marques avec assez d'avis
  { $project: {
      _id: 0, marque: "$_id", nb_avis: 1,
      note_moyenne: { $round: [{ $divide: ["$somme_notes", "$nb_avis"] }, 2] }
  } },
  { $sort: { note_moyenne: -1 } },
  { $limit: 5 }
]).toArray();
