WITH daily_copay AS (
    SELECT
        clinic_id,
        date_trunc('day', created_at) AS revenue_day,
        SUM(copay_amount)             AS daily_revenue
    FROM appointments
    GROUP BY clinic_id, date_trunc('day', created_at)
),
moving_avg AS (
    SELECT
        clinic_id,
        revenue_day,
        daily_revenue,
        AVG(daily_revenue) OVER (
            PARTITION BY clinic_id
            ORDER BY revenue_day
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS moving_avg_7day
    FROM daily_copay
)
SELECT
    clinic_id,
    revenue_day,
    daily_revenue,
    ROUND(moving_avg_7day, 2) AS moving_avg_7day,
    DENSE_RANK() OVER (
        PARTITION BY revenue_day
        ORDER BY moving_avg_7day DESC
    ) AS clinic_rank_that_day
FROM moving_avg
ORDER BY revenue_day, clinic_rank_that_day;