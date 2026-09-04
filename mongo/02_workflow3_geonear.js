// =====================================================================
// 02_workflow3_geonear.js
// Workflow 3: Nearest Mobile Nurse
// Finds the closest ACTIVE nurse ping to a given patient's coordinates.
// Run with: mongosh careconnect 02_workflow3_geonear.js
// =====================================================================

db = db.getSiblingDB("careconnect");

// Replace with the patient's real coordinates (longitude, latitude order!)
const patientLongitude = 80.2707;
const patientLatitude  = 13.0827;

const nearestNurse = db.NursePings.aggregate([
    {
        $geoNear: {
            near: {
                type: "Point",
                coordinates: [patientLongitude, patientLatitude]
            },
            distanceField: "distance_meters",
            spherical: true,
            query: { is_active: true },
            key: "location"
        }
    },
    {
        $sort: { distance_meters: 1 }
    },
    {
        $limit: 1
    },
    {
        $project: {
            _id: 0,
            nurse_id: 1,
            distance_meters: { $round: ["$distance_meters", 1] },
            location: 1,
            created_at: 1
        }
    }
]).toArray();

printjson(nearestNurse);

// For the README performance proof, run:
// db.NursePings.aggregate([...]).explain("executionStats")
// and confirm the plan shows an IXSCAN using the 2dsphere index
// (not a COLLSCAN).
