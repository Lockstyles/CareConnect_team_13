"""
Usage:
    python postgres_seeder.py

Requires:
    pip install -r requirements.txt

Set your connection string via the PG_DSN env var, or edit DEFAULT_DSN below.
"""

import os
import random
import uuid
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values
from faker import Faker

fake = Faker()

# NOTE: match this to however you actually created your database.
# You connected with: psql -U postgres "CareConnect" -f ...
# so the dbname here must match exactly (case-sensitive if quoted at creation).
DEFAULT_DSN = 'dbname=CareConnect user=postgres password=postgres host=localhost port=5432'
PG_DSN = os.environ.get("PG_DSN", DEFAULT_DSN)

N_CLINICS = 100
N_PATIENTS = 5000
N_APPOINTMENTS = 100_000
BATCH_SIZE = 5000

# Probability that a patient's single most-recent appointment is still
# "active" (WAITING or IN_CONSULTATION) rather than DISCHARGED.
ACTIVE_PROB = 0.25


def seed_clinics(cur):
    print(f"Seeding {N_CLINICS} clinics...")
    rows = []
    for _ in range(N_CLINICS):
        rows.append((
            str(uuid.uuid4()),
            fake.company() + " Clinic",
            round(random.uniform(12.90, 13.20), 6),
            round(random.uniform(80.10, 80.35), 6),
            random.random() > 0.15,
        ))
    execute_values(
        cur,
        "INSERT INTO clinics (id, name, latitude, longitude, is_accepting_patients) VALUES %s",
        rows
    )
    return [r[0] for r in rows]


def seed_patients(cur):
    print(f"Seeding {N_PATIENTS} patients...")
    rows = []
    for _ in range(N_PATIENTS):
        rows.append((
            str(uuid.uuid4()),
            fake.name(),
            round(random.uniform(50, 5000), 2),
        ))
    execute_values(
        cur,
        "INSERT INTO patients (id, name, hsa_balance) VALUES %s",
        rows
    )
    return [r[0] for r in rows]


def appointment_counts_per_patient(n_patients, n_appointments):
    """
    Distributes n_appointments across n_patients as evenly as possible,
    e.g. 100,000 / 5,000 -> 20 each, with the remainder spread over the
    first few patients.
    """
    base = n_appointments // n_patients
    remainder = n_appointments % n_patients
    counts = [base] * n_patients
    for i in range(remainder):
        counts[i] += 1
    random.shuffle(counts)
    return counts


def random_timestamps_sorted(n, days_back=180):
    """Generate n timestamps within the last `days_back` days, ascending
    (index 0 = oldest, index -1 = most recent)."""
    now = datetime.now()
    seconds_span = days_back * 24 * 3600
    offsets = sorted((random.randint(0, seconds_span) for _ in range(n)), reverse=True)
    return [now - timedelta(seconds=off) for off in offsets]


def build_patient_appointments(patient_id, count):
    """
    Builds `count` appointment rows for a single patient, guaranteeing:
      - all but the last (chronologically) are DISCHARGED
      - the last (most recent) is DISCHARGED with probability
        (1 - ACTIVE_PROB), otherwise WAITING/IN_CONSULTATION
    Returns list of dicts with keys: created_at, status
    """
    if count == 0:
        return []

    timestamps = random_timestamps_sorted(count)  # ascending, last = most recent
    statuses = ["DISCHARGED"] * (count - 1)

    if random.random() < ACTIVE_PROB:
        last_status = random.choice(["WAITING", "IN_CONSULTATION"])
    else:
        last_status = "DISCHARGED"
    statuses.append(last_status)

    return [{"created_at": ts, "status": st} for ts, st in zip(timestamps, statuses)]


def seed_appointments_and_audit(cur, patient_ids, clinic_ids):
    print(f"Seeding {N_APPOINTMENTS} appointments + matching audit logs "
          f"(respecting idx_active_consult)...")

    counts = appointment_counts_per_patient(len(patient_ids), N_APPOINTMENTS)

    appt_batch = []
    audit_batch = []
    total_inserted = 0

    def flush():
        nonlocal appt_batch, audit_batch, total_inserted
        if not appt_batch:
            return
        execute_values(
            cur,
            "INSERT INTO appointments (id, patient_id, clinic_id, copay_amount, status, created_at, discharged_at) VALUES %s",
            appt_batch
        )
        execute_values(
            cur,
            'INSERT INTO wallet_audit_logs (id, patient_id, amount_changed, action_type, balance_after, "timestamp") VALUES %s',
            audit_batch
        )
        total_inserted += len(appt_batch)
        print(f"  {total_inserted}/{N_APPOINTMENTS} appointments inserted")
        appt_batch = []
        audit_batch = []

    for patient_id, count in zip(patient_ids, counts):
        for appt in build_patient_appointments(patient_id, count):
            appt_id = str(uuid.uuid4())
            clinic_id = random.choice(clinic_ids)
            copay = round(random.uniform(10, 150), 2)

            # discharged_at must be set explicitly here: the DB trigger
            # trg_set_discharged_at only fills it in with now() if it's
            # left NULL, which would make every seeded DISCHARGED row
            # carry today's date instead of a historically spread-out
            # one, collapsing mv_clinic_monthly_discharges into a single
            # month. Simulate a discharge happening some time after
            # check-in (0-6 hours later).
            if appt["status"] == "DISCHARGED":
                discharged_at = appt["created_at"] + timedelta(hours=random.uniform(0, 6))
            else:
                discharged_at = None

            appt_batch.append((
                appt_id, patient_id, clinic_id, copay, appt["status"], appt["created_at"], discharged_at
            ))
            audit_batch.append((
                str(uuid.uuid4()),
                patient_id,
                -copay,
                "APPOINTMENT_DEDUCTION",
                round(random.uniform(0, 5000), 2),
                appt["created_at"],
            ))

            if len(appt_batch) >= BATCH_SIZE:
                flush()

    flush()  # insert any remainder


def main():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            clinic_ids = seed_clinics(cur)
            patient_ids = seed_patients(cur)
            seed_appointments_and_audit(cur, patient_ids, clinic_ids)
        conn.commit()
        print("Done. Committed all rows.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()