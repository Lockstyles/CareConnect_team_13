db = db.getSiblingDB("careconnect");

// MedicalCatalogs - flexible docs storing specialist availability and varied medication details (deliberately loose schema per patient/clinic)
db.createCollection("MedicalCatalogs", {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["clinic_id", "type"],
            properties: {
                clinic_id: { bsonType: "string", description: "references Postgres clinics.id" },
                type: { enum: ["specialist_availability", "medication"], description: "discriminator field" },
            }
        }
    },
    validationLevel: "moderate"
});

// PatientReviews - structured reviews with ratings, bedside-manner tags, and timestamps
db.createCollection("PatientReviews", {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["patient_id", "clinic_id", "rating", "tags", "created_at"],
            properties: {
                patient_id: { bsonType: "string" },
                clinic_id:  { bsonType: "string" },
                rating:     { bsonType: "int", minimum: 1, maximum: 5 },
                tags:       { bsonType: "array", items: { bsonType: "string" } },
                comment:    { bsonType: "string" },
                created_at: { bsonType: "date" }
            }
        }
    },
    validationLevel: "moderate"
});

// NursePings - real-time geospatial location logs of dispatched mobile nurses location must be stored as GeoJSON for 2dsphere indexing
db.createCollection("NursePings", {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["nurse_id", "location", "is_active", "created_at"],
            properties: {
                nurse_id:  { bsonType: "string" },
                is_active: { bsonType: "bool" },
                location: {
                    bsonType: "object",
                    required: ["type", "coordinates"],
                    properties: {
                        type: { enum: ["Point"] },
                        coordinates: {
                            bsonType: "array",
                            minItems: 2,
                            maxItems: 2,
                            items: { bsonType: "double" }   // [longitude, latitude]
                        }
                    }
                },
                created_at: { bsonType: "date" }
            }
        }
    },
    validationLevel: "moderate"
});

// Geospatial index for $geoNear (Workflow 3)
db.NursePings.createIndex({ location: "2dsphere" });

// TTL index: documents auto-expire 2 hours (7200s) after created_at
db.NursePings.createIndex({ created_at: 1 }, { expireAfterSeconds: 7200 });

// Helpful secondary indexes
db.NursePings.createIndex({ nurse_id: 1, is_active: 1 });
db.PatientReviews.createIndex({ clinic_id: 1 });
db.PatientReviews.createIndex({ rating: 1 });
db.MedicalCatalogs.createIndex({ clinic_id: 1, type: 1 });

print("Collections + indexes created.");
