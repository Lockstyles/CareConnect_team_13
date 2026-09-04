# CareConnect — On-Demand Telemedicine (Project 4)

CS6.302 Software System Development — Assignment 1: Database Design
Team 13

**GitHub Repository:** `https://github.com/Lockstyles/CareConnect_team_13`

---

## 1. Overview

CareConnect models a telemedicine platform's data layer across two databases:

- **PostgreSQL** — patients, clinics, appointments, and an immutable wallet audit trail
  (transactional, consistency-critical data).
- **MongoDB** — flexible medical catalogs, patient reviews, and real-time nurse
  location pings (schema-flexible, high-write, geospatial data).

---

## 2. Setup Instructions

### 2.1 Prerequisites

- DPostgres 16 and MongoDB 7 
- Python 3.10+ with `pip`
- brew install postgresql@16
- brew services start postgresql@16

- brew tap mongodb/brew
- brew install mongodb-community@7.0
- brew services start mongodb-community@7.0

### 2.2 Start the databases

**MacOS**
```bash
psql postgres
CREATE USER admin WITH PASSWORD 'devpass';

# Inside the psql prompt:
CREATE DATABASE "CareConnect" OWNER admin;
\q
psql -U admin -d CareConnect 

mongosh
use CareConnect
```

**Ubuntu**
```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql

curl -fsSL https://pgp.mongodb.com/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg arch=amd64] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt update
sudo apt install -y mongodb-org
sudo systemctl start mongod
sudo systemctl enable mongod

sudo -u postgres psql

# Inside the psql prompt:
CREATE USER admin WITH PASSWORD 'devpass';
CREATE DATABASE "CareConnect" OWNER admin;
\q

psql -h localhost -U admin -d CareConnect

mongosh
use CareConnect
```

### 2.3 Apply the PostgreSQL schema (run in order)

```bash
psql -h localhost -U admin -d CareConnect -f sql/01_schema_ddl.sql
psql -h localhost -U admin -d CareConnect -f sql/02_indexes.sql
psql -h localhost -U admin -d CareConnect -f sql/03_triggers_and_audit.sql
psql -h localhost -U admin -d CareConnect -f sql/04_stored_procedures.sql
psql -h localhost -U admin -d CareConnect -f sql/05_materialized_views.sql
psql -h localhost -U admin -d CareConnect -f sql/06_window_analytics.sql
```


### 2.4 Set up MongoDB collections and indexes

```bash
mongosh careconnect mongo/01_collections_and_indexes.js
```

### 2.5 Seed mock data

```bash
cd data_generation
python3 -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt

export PG_DSN='dbname=CareConnect user=admin password=devpass host=localhost port=5432'
export MONGO_URI='mongodb://localhost:27017'
export MONGO_DB_NAME='careconnect'

python postgres_seeder.py
python mongo_seeder.py
```

This generates:
- 100 clinics, 5,000 patients, 100,000 appointments, 100,000 wallet audit logs (PostgreSQL)
- 500,000 nurse pings, 5,000 patient reviews, 200 medical catalog entries (MongoDB)

### 2.6 Run the workflows

```bash
cd ..
psql -h localhost -U admin -d CareConnect -f sql/06_window_analytics.sql
mongosh careconnect mongo/02_workflow3_geonear.js
mongosh careconnect mongo/03_workflow4_facet.js
mongosh careconnect --quiet --eval '
JSON.stringify({
  workflow3_nearest_nurse: db.NursePings.aggregate([
    { $geoNear: { near: { type: "Point", coordinates: [80.2707, 13.0827] }, distanceField: "distance_meters", spherical: true, query: { is_active: true }, key: "location" } },
    { $sort: { distance_meters: 1 } },
    { $limit: 1 }
  ], { explain: "executionStats" }),
  workflow4_review_analytics: db.PatientReviews.aggregate([
    { $facet: {
        rating_buckets: [{ $group: { _id: "$rating", count: { $sum: 1 } } }],
        top_tags: [{ $unwind: "$tags" }, { $group: { _id: "$tags", count: { $sum: 1 } } }, { $sort: { count: -1 } }, { $limit: 5 }],
        overall_average: [{ $group: { _id: null, avg: { $avg: "$rating" } } }]
    }}
  ], { explain: "executionStats" })
}, null, 2)
' > performance/mongo_execution_stats.json
```

---

## 3. Assumptions

- All primary keys are `UUID`s (via `uuid-ossp`) rather than sequential integers,
  since the assignment allows either.
- `appointments.status` is implemented as a Postgres `ENUM` type rather than a
  plain `VARCHAR`, for stricter validation at the database level.
- `wallet_audit_logs.action_type` records `'DEDUCTION'` or `'CREDIT'` (renamed
  slightly from the sample `DEBIT`/`CREDIT` wording in the spec) to match the
  appointment-copay use case.
- Deleting a patient cascades to their appointments and audit logs
  (`ON DELETE CASCADE`); deleting a clinic that still has appointments is
  restricted (`ON DELETE RESTRICT`) to avoid orphaned records.
- Seed data is geographically clustered around the Chennai metro area
  (latitude 12.90–13.20, longitude 80.10–80.35) as a representative sample region.
- Appointment timestamps are randomly distributed across the last 180 days;
  nurse ping timestamps are randomly distributed across the last 4 hours so a
  meaningful fraction remain within the 2-hour TTL window at query time.
- MongoDB collections use `validationLevel: "moderate"` — new documents must
  satisfy the `$jsonSchema` validator, but this does not retroactively enforce
  structure on pre-existing documents.
- The materialized view aggregates discharge counts by **calendar month**
  (`date_trunc('month', created_at)`), matching "total monthly patient discharges."

---

## 4. Performance Proof

### 4.1 Workflow 2 — SQL Window Analytics (`EXPLAIN ANALYZE`)

```
                                                                                              QUERY PLAN                                                                                              
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 Incremental Sort  (cost=30458.95..38412.15 rows=100000 width=128) (actual time=91.971..97.814 rows=18020.00 loops=1)
   Sort Key: moving_avg.revenue_day, (dense_rank() OVER w1)
   Presorted Key: moving_avg.revenue_day
   Full-sort Groups: 181  Sort Method: quicksort  Average Memory: 29kB  Peak Memory: 29kB
   Pre-sorted Groups: 181  Sort Method: quicksort  Average Memory: 31kB  Peak Memory: 31kB
   Buffers: shared hit=68852
   ->  WindowAgg  (cost=30425.28..32675.26 rows=100000 width=128) (actual time=91.913..95.848 rows=18020.00 loops=1)
         Window: w1 AS (PARTITION BY moving_avg.revenue_day ORDER BY moving_avg.moving_avg_7day ROWS UNBOUNDED PRECEDING)
         Storage: Memory  Maximum Storage: 17kB
         Buffers: shared hit=68849
         ->  Sort  (cost=30425.26..30675.26 rows=100000 width=88) (actual time=91.907..92.241 rows=18020.00 loops=1)
               Sort Key: moving_avg.revenue_day, moving_avg.moving_avg_7day DESC
               Sort Method: quicksort  Memory: 1871kB
               Buffers: shared hit=68849
               ->  Subquery Scan on moving_avg  (cost=121.61..17332.44 rows=100000 width=88) (actual time=4.082..86.644 rows=18020.00 loops=1)
                     Buffers: shared hit=68846
                     ->  WindowAgg  (cost=121.61..17332.44 rows=100000 width=88) (actual time=4.080..85.548 rows=18020.00 loops=1)
                           Window: w1 AS (PARTITION BY appointments.clinic_id ORDER BY (date_trunc('day'::text, appointments.created_at)) RANGE BETWEEN '6 days'::interval PRECEDING AND CURRENT ROW)
                           Storage: Memory  Maximum Storage: 17kB
                           Buffers: shared hit=68846
                           ->  GroupAggregate  (cost=121.09..15582.44 rows=100000 width=56) (actual time=4.031..71.355 rows=18020.00 loops=1)
                                 Group Key: appointments.clinic_id, (date_trunc('day'::text, appointments.created_at))
                                 Buffers: shared hit=68846
                                 ->  Incremental Sort  (cost=121.09..13332.44 rows=100000 width=30) (actual time=3.986..59.709 rows=100000.00 loops=1)
                                       Sort Key: appointments.clinic_id, (date_trunc('day'::text, appointments.created_at))
                                       Presorted Key: appointments.clinic_id
                                       Full-sort Groups: 100  Sort Method: quicksort  Average Memory: 28kB  Peak Memory: 28kB
                                       Pre-sorted Groups: 100  Sort Method: quicksort  Average Memory: 97kB  Peak Memory: 97kB
                                       Buffers: shared hit=68846
                                       ->  Index Scan using idx_appointments_clinic_id on appointments  (cost=0.29..7097.55 rows=100000 width=30) (actual time=0.050..44.368 rows=100000.00 loops=1)
                                             Index Searches: 1
                                             Buffers: shared hit=68843
 Planning:
   Buffers: shared hit=191
 Planning Time: 2.035 ms
 Execution Time: 98.421 ms
(36 rows)
```

**Verdict:** the base scan on `appointments` uses `Index Scan using idx_appointments_clinic_id`
— not a `Seq Scan` — confirming the query hits the index from `02_indexes.sql`.
Total execution time: **91.6ms** over 100,000 appointment rows.

### 4.2 Workflow 3 & 4

```

{
  "workflow3_nearest_nurse": {
    "explainVersion": "1",
    "stages": [
      {
        "$geoNearCursor": {
          "queryPlanner": {
            "namespace": "careconnect.NursePings",
            "indexFilterSet": false,
            "parsedQuery": {
              "$and": [
                {
                  "is_active": {
                    "$eq": true
                  }
                },
                {
                  "location": {
                    "$nearSphere": {
                      "type": "Point",
                      "coordinates": [
                        80.2707,
                        13.0827
                      ]
                    }
                  }
                }
              ]
            },

The output file was too long so these are the first 20 lines, and the rest of the output is in the mongo_execution_stats.json

```

## 5. Repository Structure

```
team_13_a1/
├── README.md
├── docs/
│   ├── relational_erd.png
│   └── mongo_schema_map.json
├── sql/
│   ├── 01_schema_ddl.sql
│   ├── 02_indexes.sql
│   ├── 03_triggers_and_audit.sql
│   ├── 04_stored_procedures.sql
│   ├── 05_materialized_views.sql
│   └── 06_window_analytics.sql
├── mongo/
│   ├── 01_collections_and_indexes.js
│   ├── 02_workflow3_geonear.js
│   └── 03_workflow4_facet.js
├── data_generation/
│   ├── postgres_seeder.py
│   ├── mongo_seeder.py
│   └── requirements.txt
└── performance/
    ├── postgres_explain_analyzes.txt
    └── mongo_execution_stats.json
```