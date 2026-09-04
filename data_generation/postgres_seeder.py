"""
Usage:
    python postgres_seeder.py

Requires:
    pip install -r requirements.txt

Set your connection string using PG_DSN, for example:

    export PG_DSN='dbname=CareConnect user=postgres password=YOUR_PASSWORD host=localhost port=5432'
"""

import os
import random
import uuid
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values
from faker import Faker


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

fake = Faker()

DEFAULT_DSN = (
    "dbname=CareConnect "
    "user=postgres "
    "password=aditya "
    "host=localhost "
    "port=5432"
)

PG_DSN = os.environ.get("PG_DSN", DEFAULT_DSN)

N_CLINICS = 100
N_PATIENTS = 5_000
N_APPOINTMENTS = 100_000

BATCH_SIZE = 5_000

# Exact desired status counts
N_WAITING = 2_500
N_IN_CONSULTATION = 2_500
N_DISCHARGED = 95_000


# ---------------------------------------------------------
# Validation
# ---------------------------------------------------------

if N_WAITING + N_IN_CONSULTATION + N_DISCHARGED != N_APPOINTMENTS:
    raise ValueError(
        "Status counts must add up to N_APPOINTMENTS"
    )

if N_WAITING + N_IN_CONSULTATION > N_PATIENTS:
    raise ValueError(
        "Number of active appointments cannot exceed number of patients "
        "because idx_active_consult allows only one active appointment "
        "per patient."
    )


# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------

def random_timestamp_within_days(days_back=180):
    """
    Returns a random timestamp within the last `days_back` days.
    """
    seconds_back = random.randint(
        0,
        days_back * 24 * 60 * 60
    )

    return datetime.now() - timedelta(
        seconds=seconds_back
    )


def generate_statuses():
    """
    Creates exactly:

        95,000 DISCHARGED
         2,500 WAITING
         2,500 IN_CONSULTATION

    Then shuffles them so they are distributed randomly.
    """

    statuses = (
        ["DISCHARGED"] * N_DISCHARGED
        + ["WAITING"] * N_WAITING
        + ["IN_CONSULTATION"] * N_IN_CONSULTATION
    )

    random.shuffle(statuses)

    return statuses


# ---------------------------------------------------------
# Clinics
# ---------------------------------------------------------

def seed_clinics(cur):
    print(f"Seeding {N_CLINICS} clinics...")

    rows = []

    for _ in range(N_CLINICS):
        rows.append(
            (
                str(uuid.uuid4()),
                fake.company() + " Clinic",

                # Chennai-area latitude
                round(
                    random.uniform(12.90, 13.20),
                    6
                ),

                # Chennai-area longitude
                round(
                    random.uniform(80.10, 80.35),
                    6
                ),

                # ~85% accepting patients
                random.random() > 0.15,
            )
        )

    execute_values(
        cur,
        """
        INSERT INTO clinics
            (
                id,
                name,
                latitude,
                longitude,
                is_accepting_patients
            )
        VALUES %s
        """,
        rows
    )

    return [row[0] for row in rows]


# ---------------------------------------------------------
# Patients
# ---------------------------------------------------------

def seed_patients(cur):
    print(f"Seeding {N_PATIENTS} patients...")

    rows = []

    for _ in range(N_PATIENTS):
        rows.append(
            (
                str(uuid.uuid4()),
                fake.name(),
                round(
                    random.uniform(50, 5000),
                    2
                ),
            )
        )

    execute_values(
        cur,
        """
        INSERT INTO patients
            (
                id,
                name,
                hsa_balance
            )
        VALUES %s
        """,
        rows
    )

    return [row[0] for row in rows]


# ---------------------------------------------------------
# Appointments + Audit Logs
# ---------------------------------------------------------

def seed_appointments_and_audit(
    cur,
    patient_ids,
    clinic_ids
):
    """
    Generates exactly:

        95,000 DISCHARGED
         2,500 WAITING
         2,500 IN_CONSULTATION

    There are 5,000 active appointments total.

    Each active appointment is assigned to a DIFFERENT patient.

    Therefore:

        WAITING + IN_CONSULTATION
        <= number of patients

    and idx_active_consult is never violated.
    """

    print(
        f"Seeding {N_APPOINTMENTS:,} appointments "
        f"+ {N_APPOINTMENTS:,} audit logs..."
    )

    # -----------------------------------------------------
    # Select unique patients for active appointments
    # -----------------------------------------------------

    active_count = (
        N_WAITING
        + N_IN_CONSULTATION
    )

    active_patients = random.sample(
        patient_ids,
        active_count
    )

    waiting_patients = active_patients[
        :N_WAITING
    ]

    consultation_patients = active_patients[
        N_WAITING:
    ]

    # -----------------------------------------------------
    # Create patient -> active status mapping
    # -----------------------------------------------------

    active_status_by_patient = {}

    for patient_id in waiting_patients:
        active_status_by_patient[
            patient_id
        ] = "WAITING"

    for patient_id in consultation_patients:
        active_status_by_patient[
            patient_id
        ] = "IN_CONSULTATION"

    # -----------------------------------------------------
    # Generate appointments
    # -----------------------------------------------------

    # Start with all discharged appointments.
    statuses = (
        ["DISCHARGED"] * N_DISCHARGED
    )

    # We will explicitly create active appointments
    # for selected patients.
    active_appointments = []

    for patient_id, status in active_status_by_patient.items():

        active_appointments.append(
            (
                patient_id,
                status
            )
        )

    # Shuffle discharged appointments so they don't have
    # a predictable ordering.
    random.shuffle(statuses)

    # -----------------------------------------------------
    # We need exactly 100k appointments.
    #
    # Every active patient receives one active appointment.
    # The remaining appointments are distributed as
    # historical DISCHARGED appointments.
    # -----------------------------------------------------

    appointment_records = []

    # -----------------------------------------------------
    # Create active appointments first
    # -----------------------------------------------------

    for patient_id, status in active_appointments:

        appointment_records.append(
            (
                patient_id,
                status
            )
        )

    # -----------------------------------------------------
    # Create discharged appointments.
    #
    # Every patient gets historical appointments.
    # -----------------------------------------------------

    remaining_count = (
        N_APPOINTMENTS
        - len(active_appointments)
    )

    for _ in range(remaining_count):

        patient_id = random.choice(
            patient_ids
        )

        appointment_records.append(
            (
                patient_id,
                "DISCHARGED"
            )
        )

    # -----------------------------------------------------
    # Shuffle all appointments
    # -----------------------------------------------------

    random.shuffle(
        appointment_records
    )

    # -----------------------------------------------------
    # Insert in batches
    # -----------------------------------------------------

    appt_batch = []
    audit_batch = []

    total_inserted = 0

    for patient_id, status in appointment_records:

        appointment_id = str(
            uuid.uuid4()
        )

        clinic_id = random.choice(
            clinic_ids
        )

        copay = round(
            random.uniform(10, 150),
            2
        )

        created_at = (
            random_timestamp_within_days(180)
        )

        # Appointment
        appt_batch.append(
            (
                appointment_id,
                patient_id,
                clinic_id,
                copay,
                status,
                created_at,
            )
        )

        # Matching audit record
        audit_batch.append(
            (
                str(uuid.uuid4()),
                patient_id,
                -copay,
                "APPOINTMENT_DEDUCTION",
                round(
                    random.uniform(0, 5000),
                    2
                ),
                created_at,
            )
        )

        # -------------------------------------------------
        # Flush batch
        # -------------------------------------------------

        if len(appt_batch) >= BATCH_SIZE:

            execute_values(
                cur,
                """
                INSERT INTO appointments
                    (
                        id,
                        patient_id,
                        clinic_id,
                        copay_amount,
                        status,
                        created_at
                    )
                VALUES %s
                """,
                appt_batch
            )

            execute_values(
                cur,
                """
                INSERT INTO wallet_audit_logs
                    (
                        id,
                        patient_id,
                        amount_changed,
                        action_type,
                        balance_after,
                        "timestamp"
                    )
                VALUES %s
                """,
                audit_batch
            )

            total_inserted += len(
                appt_batch
            )

            print(
                f"  {total_inserted:,}/"
                f"{N_APPOINTMENTS:,} "
                f"appointments inserted"
            )

            appt_batch = []
            audit_batch = []

    # -----------------------------------------------------
    # Insert remaining rows
    # -----------------------------------------------------

    if appt_batch:

        execute_values(
            cur,
            """
            INSERT INTO appointments
                (
                    id,
                    patient_id,
                    clinic_id,
                    copay_amount,
                    status,
                    created_at
                )
            VALUES %s
            """,
            appt_batch
        )

        execute_values(
            cur,
            """
            INSERT INTO wallet_audit_logs
                (
                    id,
                    patient_id,
                    amount_changed,
                    action_type,
                    balance_after,
                    "timestamp"
                )
            VALUES %s
            """,
            audit_batch
        )

        total_inserted += len(
            appt_batch
        )

        print(
            f"  {total_inserted:,}/"
            f"{N_APPOINTMENTS:,} "
            f"appointments inserted"
        )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():

    print("========================================")
    print("CareConnect PostgreSQL Seeder")
    print("========================================")

    print(
        f"Target appointments: "
        f"{N_APPOINTMENTS:,}"
    )

    print(
        f"  DISCHARGED: "
        f"{N_DISCHARGED:,}"
    )

    print(
        f"  WAITING: "
        f"{N_WAITING:,}"
    )

    print(
        f"  IN_CONSULTATION: "
        f"{N_IN_CONSULTATION:,}"
    )

    print()

    conn = psycopg2.connect(
        PG_DSN
    )

    conn.autocommit = False

    try:

        with conn.cursor() as cur:

            clinic_ids = seed_clinics(
                cur
            )

            patient_ids = seed_patients(
                cur
            )

            seed_appointments_and_audit(
                cur,
                patient_ids,
                clinic_ids
            )

        conn.commit()

        print()
        print("========================================")
        print("Seeding completed successfully.")
        print("========================================")

        print(
            f"Clinics: "
            f"{N_CLINICS:,}"
        )

        print(
            f"Patients: "
            f"{N_PATIENTS:,}"
        )

        print(
            f"Appointments: "
            f"{N_APPOINTMENTS:,}"
        )

        print(
            f"Wallet audit logs: "
            f"{N_APPOINTMENTS:,}"
        )

    except Exception:

        conn.rollback()

        print()
        print(
            "Seeding failed. "
            "All changes have been rolled back."
        )

        raise

    finally:

        conn.close()


if __name__ == "__main__":
    main()

