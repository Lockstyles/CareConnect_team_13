// =====================================================================
// Workflow 4: Multi-Faceted Review Analytics
// Uses $facet to compute, in a single pass over PatientReviews:
//   1. rating_buckets     - count of reviews per rating (1-5)
//   2. top_sentiment_tags - most frequent bedside-manner tags ($unwind)
//   3. global_average     - overall average rating across all reviews
// =====================================================================

db = db.getSiblingDB("careconnect");

const reviewAnalytics = db.PatientReviews.aggregate([
    {
        $facet: {
            rating_buckets: [
                { $group: { _id: "$rating", count: { $sum: 1 } } },
                { $sort: { _id: 1 } }
            ],
            top_sentiment_tags: [
                { $unwind: "$tags" },
                { $group: { _id: "$tags", count: { $sum: 1 } } },
                { $sort: { count: -1 } },
                { $limit: 10 }
            ],
            global_average: [
                {
                    $group: {
                        _id: null,
                        avg_rating: { $avg: "$rating" },
                        total_reviews: { $sum: 1 }
                    }
                },
                {
                    $project: {
                        _id: 0,
                        avg_rating: { $round: ["$avg_rating", 2] },
                        total_reviews: 1
                    }
                }
            ]
        }
    }
]).toArray();

printjson(reviewAnalytics);
