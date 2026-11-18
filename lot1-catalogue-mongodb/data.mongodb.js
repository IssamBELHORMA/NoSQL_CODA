// Lot 1 — Catalogue Produits (MongoDB)
// Création des collections

use('ldlc');

// Repartir de zéro à chaque exécution
db.produits.drop();
db.marques.drop();
db.avis.drop();

// ---------------------------------------------------------------------
// Collection produits avec validation souple :
// champs communs obligatoires, champs supplémentaires autorisés
// ---------------------------------------------------------------------
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

db.getCollectionInfos({ name: "produits" })[0].options.validator;