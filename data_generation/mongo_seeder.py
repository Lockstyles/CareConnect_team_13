"""
- Seeds MongoDB with mock data for CareConnect.
- Generates 500000 NursePings geospatial telemetry documents, plus a smaller
  batch of PatientReviews and MedicalCatalogs so Workflow 4 has data to
  aggregate over.

Set connection string through the MONGO_URI env var or edit the DEFAULT_URI.
"""

import os
import random
import uuid
from datetime import datetime, timedelta

from pymongo import MongoClient, InsertOne
from faker import Faker

fake = Faker()

DEFAULT_URI = "mongodb://localhost:27017"
MONGO_URI = os.environ.get("MONGO_URI", DEFAULT_URI)

DB_NAME = os.environ.get("MONGO_DB_NAME", "careconnect")

N_NURSE_PINGS = 500_000
N_PATIENT_REVIEWS = 5_000
N_MEDICAL_CATALOG_ENTRIES = 200
BATCH_SIZE = 5000

N_NURSES = 300   # distinct nurse_ids pinging repeatedly

# Coordinates for the Chennai metro area bounding box
LAT_MIN, LAT_MAX = 12.90, 13.20
LNG_MIN, LNG_MAX = 80.10, 80.35

TAG_POOL = [
    "friendly", "attentive", "rushed", "professional", "compassionate",
    "long_wait", "clear_communication", "punctual", "thorough", "dismissive"
]


def random_point():
    lng = round(random.uniform(LNG_MIN, LNG_MAX), 6)
    lat = round(random.uniform(LAT_MIN, LAT_MAX), 6)
    return {"type": "Point", "coordinates": [lng, lat]}


def seed_nurse_pings(db):
    print(f"Seeding {N_NURSE_PINGS} NursePings documents...")
    nurse_ids = [str(uuid.uuid4()) for _ in range(N_NURSES)]
    coll = db.NursePings

    total_inserted = 0
    while total_inserted < N_NURSE_PINGS:
        batch_n = min(BATCH_SIZE, N_NURSE_PINGS - total_inserted)
        ops = []
        for _ in range(batch_n):
            # Recent timestamps so a meaningful fraction survive the 2hr TTL
            created_at = datetime.utcnow() - timedelta(seconds=random.randint(0, 3600 * 4))
            doc = {
                "nurse_id": random.choice(nurse_ids),
                "location": random_point(),
                "is_active": random.random() > 0.2,
                "created_at": created_at,
            }
            ops.append(InsertOne(doc))

        coll.bulk_write(ops, ordered=False)
        total_inserted += batch_n
        print(f"  {total_inserted}/{N_NURSE_PINGS} NursePings inserted")


def seed_patient_reviews(db):
    print(f"Seeding {N_PATIENT_REVIEWS} PatientReviews documents...")
    coll = db.PatientReviews
    ops = []
    for _ in range(N_PATIENT_REVIEWS):
        doc = {
            "patient_id": str(uuid.uuid4()),
            "clinic_id": str(uuid.uuid4()),
            "rating": random.randint(1, 5),
            "tags": random.sample(TAG_POOL, k=random.randint(1, 4)),
            "comment": fake.sentence(nb_words=12),
            "created_at": datetime.utcnow() - timedelta(days=random.randint(0, 180)),
        }
        ops.append(InsertOne(doc))
        if len(ops) >= BATCH_SIZE:
            coll.bulk_write(ops, ordered=False)
            ops = []
    if ops:
        coll.bulk_write(ops, ordered=False)


def seed_medical_catalogs(db):
    print(f"Seeding {N_MEDICAL_CATALOG_ENTRIES} MedicalCatalogs documents...")
    coll = db.MedicalCatalogs
    ops = []
    for i in range(N_MEDICAL_CATALOG_ENTRIES):
        if i % 2 == 0:
            doc = {
                "clinic_id": str(uuid.uuid4()),
                "type": "specialist_availability",
                "specialist_name": fake.name(),
                "specialty": random.choice(["Cardiology", "Dermatology", "Pediatrics", "General Medicine"]),
                "available_slots": [fake.time() for _ in range(random.randint(1, 5))],
            }
        else:
            doc = {
                "clinic_id": str(uuid.uuid4()),
                "type": "medication",
                "name": fake.word().capitalize() + random.choice(["ol", "ine", "cillin", "azole"]),
                "dosage_mg": random.choice([50, 100, 250, 500]),
                "in_stock": random.randint(0, 500),
            }
        ops.append(InsertOne(doc))
    coll.bulk_write(ops, ordered=False)


def main():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    seed_nurse_pings(db)
    seed_patient_reviews(db)
    seed_medical_catalogs(db)

    print("Done.")
    client.close()


if __name__ == "__main__":
    main()
