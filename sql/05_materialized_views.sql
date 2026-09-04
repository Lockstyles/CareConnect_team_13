DROP MATERIALIZED VIEW IF EXISTS mv_clinic_monthly_discharges;

CREATE MATERIALIZED VIEW mv_clinic_monthly_discharges AS
SELECT
    c.id                               AS clinic_id,
    c.name                             AS clinic_name,
    date_trunc('month', a.discharged_at) AS discharge_month,
    COUNT(*)                          AS total_discharges
FROM clinics c
JOIN appointments a
    ON a.clinic_id = c.id
   AND a.status = 'DISCHARGED'
GROUP BY c.id, c.name, date_trunc('month', a.discharged_at)
WITH NO DATA;

-- REFRESH CONCURRENTLY requires a UNIQUE index on the view
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_clinic_monthly_discharges_uq
    ON mv_clinic_monthly_discharges (clinic_id, discharge_month);

CREATE OR REPLACE FUNCTION refresh_clinic_monthly_discharges()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_clinic_monthly_discharges;
END;
$$ LANGUAGE plpgsql;

-- First-time population (CONCURRENTLY can't run on an empty/never-populated view)
REFRESH MATERIALIZED VIEW mv_clinic_monthly_discharges;
