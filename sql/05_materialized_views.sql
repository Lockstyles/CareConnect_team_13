CREATE MATERIALIZED VIEW IF NOT EXISTS mv_clinic_monthly_discharges AS
SELECT
    c.id                                  AS clinic_id,
    c.name                                AS clinic_name,
    date_trunc('month', a.created_at)     AS discharge_month,
    COUNT(*) FILTER (WHERE a.status = 'DISCHARGED') AS total_discharges
FROM clinics c
JOIN appointments a ON a.clinic_id = c.id
GROUP BY c.id, c.name, date_trunc('month', a.created_at)
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_clinic_monthly_discharges_uq
    ON mv_clinic_monthly_discharges (clinic_id, discharge_month);

CREATE OR REPLACE FUNCTION refresh_clinic_monthly_discharges()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_clinic_monthly_discharges;
END;
$$ LANGUAGE plpgsql;

REFRESH MATERIALIZED VIEW mv_clinic_monthly_discharges;
