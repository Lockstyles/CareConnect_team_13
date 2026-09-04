CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'appointment_status') THEN
        CREATE TYPE appointment_status AS ENUM ('WAITING', 'IN_CONSULTATION', 'DISCHARGED');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS clinics (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                  VARCHAR(150) NOT NULL,
    latitude              DECIMAL(9,6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude             DECIMAL(9,6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    is_accepting_patients BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS patients (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(150) NOT NULL,
    hsa_balance DECIMAL(10,2) NOT NULL DEFAULT 0.00 CHECK (hsa_balance >= 0.00)
);

-- ---------------------------------------------------------------------
-- appointments
-- discharged_at: set automatically by trg_set_discharged_at (see
-- 03_triggers_and_audit.sql) whenever status transitions to/is inserted
-- as DISCHARGED. Used by mv_clinic_monthly_discharges to bucket by the
-- actual discharge event rather than the appointment's creation time.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appointments (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id     UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    clinic_id      UUID NOT NULL REFERENCES clinics(id)  ON DELETE RESTRICT,
    copay_amount   DECIMAL(10,2) NOT NULL CHECK (copay_amount >= 0.00),
    status         appointment_status NOT NULL DEFAULT 'WAITING',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    discharged_at  TIMESTAMPTZ
);

-- ---------------------------------------------------------------------
-- wallet_audit_logs
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wallet_audit_logs (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id     UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    amount_changed DECIMAL(10,2) NOT NULL,
    action_type    VARCHAR(50)  NOT NULL,   -- e.g. 'APPOINTMENT_DEDUCTION', 'TOPUP', 'REFUND'
    balance_after  DECIMAL(10,2) NOT NULL,
    "timestamp"    TIMESTAMPTZ NOT NULL DEFAULT now()
);