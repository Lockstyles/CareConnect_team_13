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
