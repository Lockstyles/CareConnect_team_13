CREATE UNIQUE INDEX IF NOT EXISTS idx_active_consult
    ON appointments (patient_id)
    WHERE status IN ('WAITING', 'IN_CONSULTATION');

CREATE INDEX IF NOT EXISTS idx_appointments_clinic_id
    ON appointments (clinic_id);

CREATE INDEX IF NOT EXISTS idx_appointments_created_at
    ON appointments (created_at);

CREATE INDEX IF NOT EXISTS idx_appointments_clinic_created
    ON appointments (clinic_id, created_at);

CREATE INDEX IF NOT EXISTS idx_wallet_audit_logs_patient_id
    ON wallet_audit_logs (patient_id);
