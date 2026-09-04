CREATE OR REPLACE FUNCTION log_hsa_balance_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.hsa_balance IS DISTINCT FROM OLD.hsa_balance THEN
        INSERT INTO wallet_audit_logs (patient_id, amount_changed, action_type, balance_after, "timestamp")
        VALUES (
            NEW.id,
            NEW.hsa_balance - OLD.hsa_balance,
            CASE
                WHEN NEW.hsa_balance < OLD.hsa_balance THEN 'DEDUCTION'
                ELSE 'CREDIT'
            END,
            NEW.hsa_balance,
            now()
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_log_hsa_balance_change ON patients;

CREATE TRIGGER trg_log_hsa_balance_change
    AFTER UPDATE ON patients
    FOR EACH ROW
    EXECUTE FUNCTION log_hsa_balance_change();

-- ---------------------------------------------------------------------
-- 2. Enforce immutability on wallet_audit_logs
-- Previously this table had no protection: any role with UPDATE/DELETE
-- privileges could alter or erase audit history after the fact, which
-- defeats the purpose of an audit trail. This trigger makes the table
-- genuinely append-only at the database level, regardless of grants.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION prevent_audit_log_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'wallet_audit_logs is append-only: % is not permitted on existing rows (row id %)',
        TG_OP,
        COALESCE(OLD.id, NEW.id);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_audit_log_modification ON wallet_audit_logs;

CREATE TRIGGER trg_prevent_audit_log_modification
    BEFORE UPDATE OR DELETE ON wallet_audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_log_modification();

-- Defense in depth: also revoke the privileges directly, in case the
-- table is ever queried by a role where triggers might be disabled
-- (e.g. via ALTER TABLE ... DISABLE TRIGGER by a superuser).
REVOKE UPDATE, DELETE ON wallet_audit_logs FROM PUBLIC;

-- ---------------------------------------------------------------------
-- 3. Stamp appointments.discharged_at when status transitions to DISCHARGED
-- Needed because the materialized view was previously grouping "monthly
-- discharges" by created_at (appointment creation time), not by when the
-- discharge actually happened -- those are two different events. This
-- trigger captures the real discharge timestamp, whether the row is
-- inserted already DISCHARGED (as the seeder does) or transitions to it
-- via UPDATE (as a real application would do).
-- Requires: ALTER TABLE appointments ADD COLUMN discharged_at TIMESTAMPTZ;
-- (see 01_schema_ddl.sql / 07_migration_existing_db.sql)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_discharged_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'DISCHARGED' THEN
        IF TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'DISCHARGED' THEN
            NEW.discharged_at := COALESCE(NEW.discharged_at, now());
        END IF;
    ELSE
        NEW.discharged_at := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_set_discharged_at ON appointments;

CREATE TRIGGER trg_set_discharged_at
    BEFORE INSERT OR UPDATE ON appointments
    FOR EACH ROW
    EXECUTE FUNCTION set_discharged_at();
