// Lot 1 — Catalogue Produits (MongoDB)
// Création des collections et transformation des données brutes
// Prérequis : avoir lancé import_raw.ps1 (collections raw_*)

use('ldlc');

// Repartir de zéro à chaque exécution
db.produits.drop();
db.marques.drop();
db.avis.drop();

// Collection produits avec validation souple :
// champs communs obligatoires, champs supplémentaires autorisés
db.createCollection("produits", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "nom", "prix", "stock", "categorie"],
      properties: {
        sku:   { bsonType: "string" },
        nom:   { bsonType: "string" },
        prix:  { bsonType: ["double", "int"], minimum: 0 },
        stock: { bsonType: "int", minimum: 0 },
        categorie: {
          bsonType: "object",
          required: ["nom", "chemin"],
          properties: {
            nom:    { bsonType: "string" },
            chemin: { bsonType: "array", items: { bsonType: "string" } }
          }
        }
      }
    }
  }
});

// Transformation des données brutes -> produits
const TAUX_USD_EUR = 0.92;   // hypothèse : taux de conversion fixe

const CATEGORIES = [
  { raw: "raw_cpu",          nom: "Processeurs",             chemin: ["Composants", "Processeurs"],             prefixe: "CPU"   },
  { raw: "raw_motherboard",  nom: "Cartes mères",            chemin: ["Composants", "Cartes mères"],            prefixe: "MB"    },
  { raw: "raw_memory",       nom: "Mémoire",                 chemin: ["Composants", "Mémoire"],                 prefixe: "RAM"   },
  { raw: "raw_video_card",   nom: "Cartes graphiques",       chemin: ["Composants", "Cartes graphiques"],       prefixe: "GPU"   },
  { raw: "raw_case",         nom: "Boîtiers",                chemin: ["Composants", "Boîtiers"],                prefixe: "CASE"  },
  { raw: "raw_power_supply", nom: "Alimentations",           chemin: ["Composants", "Alimentations"],           prefixe: "PSU"   },
  { raw: "raw_keyboard",     nom: "Claviers",                chemin: ["Périphériques", "Claviers"],             prefixe: "KB"    },
  { raw: "raw_mouse",        nom: "Souris",                  chemin: ["Périphériques", "Souris"],               prefixe: "MOUSE" },
  { raw: "raw_monitor",      nom: "Écrans",                  chemin: ["Périphériques", "Écrans"],               prefixe: "MON"   },
  { raw: "raw_headphones",   nom: "Casques audio",           chemin: ["Périphériques", "Casques audio"],        prefixe: "HEAD"  },
  { raw: "raw_os",           nom: "Systèmes d'exploitation", chemin: ["Logiciels", "Systèmes d'exploitation"],  prefixe: "OS"    }
];

// Marques dont le nom contient deux mots
const MARQUES_DEUX_MOTS = ["Fractal Design", "Cooler Master", "Western Digital", "be quiet!",
                           "Lian Li", "Silicon Power", "Turtle Beach", "Mad Catz", "Red Hat", "Super Flower"];

// Index unique sur sku : nécessaire pour $merge (on: "sku")
db.produits.createIndex({ sku: 1 }, { unique: true });

function pipelineTransformation(c) {
  return [
    // 1. Garder uniquement les produits avec un nom et un prix valides
    { $match: { name: { $type: "string" }, price: { $type: "number", $gt: 0 } } },

    // 2. Extraire la marque à partir du nom
    { $addFields: { _mots: { $split: ["$name", " "] } } },
    { $addFields: {
        _deuxMots: { $concat: [
          { $arrayElemAt: ["$_mots", 0] }, " ",
          { $ifNull: [{ $arrayElemAt: ["$_mots", 1] }, ""] }
        ] }
    } },
    { $addFields: {
        _marque: { $cond: [
          { $in: ["$_deuxMots", MARQUES_DEUX_MOTS] },
          "$_deuxMots",
          { $arrayElemAt: ["$_mots", 0] }
        ] },
        _suffixe: { $toUpper: { $substrCP: [{ $toString: "$_id" }, 14, 10] } }
    } },

    // 3. Construire le document au format du modèle
    { $project: {
        _id: 0,
        sku:  { $concat: [c.prefixe, "-", "$_suffixe"] },
        nom:  "$name",
        slug: { $concat: [
          { $replaceAll: { input: { $toLower: "$name" }, find: " ", replacement: "-" } },
          "-", { $toLower: "$_suffixe" }
        ] },
        prix:   { $round: [{ $multiply: ["$price", TAUX_USD_EUR] }, 2] },
        devise: { $literal: "EUR" },
        stock:  { $toInt: { $floor: { $multiply: [{ $rand: {} }, 200] } } },
        schema_version: { $literal: 1 },
        categorie: { $literal: { nom: c.nom, chemin: c.chemin } },
        marque: {
          _id: { $concat: ["M_", { $toUpper: { $replaceAll: { input: "$_marque", find: " ", replacement: "_" } } }] },
          nom: "$_marque"
        },
        // Attribute pattern : tous les champs spécifiques -> [{ k, v }]
        specs: {
          $map: {
            input: {
              $filter: {
                input: { $objectToArray: "$$ROOT" },
                as: "a",
                cond: { $and: [
                  { $not: [{ $in: ["$$a.k", ["_id", "name", "price", "_mots", "_deuxMots", "_marque", "_suffixe"]] }] },
                  { $ne: ["$$a.v", null] }
                ] }
              }
            },
            as: "a",
            in: { k: "$$a.k", v: "$$a.v" }
          }
        },
        stats_avis:   { $literal: { nb: 0, somme: 0, moyenne: null } },
        avis_recents: { $literal: [] },
        compatibles:  { $literal: [] },
        source: { dataset: { $literal: "pc-part-dataset" }, raw_collection: { $literal: c.raw }, raw_id: "$_id" }
    } },

    // 4. Écrire dans produits (le validateur $jsonSchema s'applique)
    { $merge: { into: "produits", on: "sku", whenMatched: "replace", whenNotMatched: "insert" } }
  ];
}

CATEGORIES.forEach(c => db.getCollection(c.raw).aggregate(pipelineTransformation(c)));

// Référentiel des marques, généré à partir des produits
db.produits.aggregate([
  { $group: {
      _id: "$marque._id",
      nom: { $first: "$marque.nom" },
      nb_produits: { $sum: 1 },
      categories: { $addToSet: "$categorie.nom" }
  } },
  { $sort: { nb_produits: -1 } },
  { $out: "marques" }
]);

// Vérification
({
  produits: db.produits.countDocuments(),
  marques: db.marques.countDocuments(),
  par_categorie: db.produits.aggregate([
    { $group: { _id: "$categorie.nom", nb: { $sum: 1 } } },
    { $sort: { nb: -1 } }
  ]).toArray(),
  top_marques: db.marques.find({}, { nom: 1, nb_produits: 1 }).limit(5).toArray(),
  exemple: db.produits.findOne({ "categorie.nom": "Processeurs" })
});