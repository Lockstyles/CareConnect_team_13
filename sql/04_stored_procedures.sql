CREATE OR REPLACE PROCEDURE book_appointment(
    p_patient_id   UUID,
    p_clinic_id    UUID,
    p_copay_amount DECIMAL(10,2)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_balance DECIMAL(10,2);
    v_clinic_open      BOOLEAN;
BEGIN
    BEGIN  -- inner block: establishes the implicit SAVEPOINT for atomicity

        -- Lock the patient row so two concurrent bookings can't both
        -- read the same starting balance
        SELECT hsa_balance INTO v_current_balance
        FROM patients
        WHERE id = p_patient_id
        FOR UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Patient % does not exist', p_patient_id;
        END IF;

        SELECT is_accepting_patients INTO v_clinic_open
        FROM clinics
        WHERE id = p_clinic_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Clinic % does not exist', p_clinic_id;
        END IF;

        IF NOT v_clinic_open THEN
            RAISE EXCEPTION 'Clinic % is not currently accepting patients', p_clinic_id;
        END IF;

        IF v_current_balance < p_copay_amount THEN
            RAISE EXCEPTION 'Insufficient HSA balance: has %, needs %', v_current_balance, p_copay_amount;
        END IF;

        -- Deduct balance -> fires trg_log_hsa_balance_change -> audit row written
        UPDATE patients
        SET hsa_balance = hsa_balance - p_copay_amount
        WHERE id = p_patient_id;

        -- Create the appointment (also fires trg_set_discharged_at, no-op here since status=WAITING)
        INSERT INTO appointments (patient_id, clinic_id, copay_amount, status)
        VALUES (p_patient_id, p_clinic_id, p_copay_amount, 'WAITING');

    EXCEPTION
        WHEN OTHERS THEN
            -- PL/pgSQL has already rolled back to the SAVEPOINT taken at
            -- the start of this block, undoing the UPDATE and INSERT
            -- above. Re-raise so the failure propagates to the caller
            -- and the CALL as a whole is reported as failed.
            RAISE;
    END;
END;
$$;

