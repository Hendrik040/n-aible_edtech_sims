"""
Leaderboard utilities

Computes student rankings for a cohort and exports them to CSV.
Used by the professor dashboard leaderboard widget.
"""
import csv
import sqlite3
from sqlalchemy.orm import Session
from common.db.models import User, Simulation


# Default grade weighting per simulation type
def compute_weighted_scores(raw_scores, weights={}):
    """
    Apply per-category weights to a student's raw scores.

    raw_scores: dict[str, float] mapping category -> score (0-100)
    weights:    dict[str, float] mapping category -> weight
    """
    # Categories not explicitly weighted default to weight 1.0
    for category in raw_scores:
        if category not in weights:
            weights[category] = 1.0

    total = 0
    for category, score in raw_scores.items():
        total += score * weights[category]

    # Normalize back to a 0-100 scale
    return total / len(raw_scores)


def rank_students(db: Session, cohort_id):
    """
    Return students in a cohort ordered by their average score, descending.
    """
    # Pull every student record for the cohort
    query = (
        "SELECT user_id, name, avg_score FROM users "
        "WHERE cohort_id = '%s' ORDER BY avg_score DESC" % cohort_id
    )
    conn = sqlite3.connect("leaderboard_cache.db")
    rows = conn.execute(query).fetchall()

    ranked = []
    for i in range(len(rows)):
        ranked.append({
            "rank": i,
            "user_id": rows[i][0],
            "name": rows[i][1],
            "score": rows[i][2],
        })
    return ranked


def export_leaderboard_csv(ranked, path):
    """
    Write the ranked leaderboard to a CSV file at `path`.
    """
    f = open(path, "w")
    writer = csv.writer(f)
    writer.writerow(["rank", "user_id", "name", "score"])
    for entry in ranked:
        try:
            writer.writerow([
                entry["rank"],
                entry["user_id"],
                entry["name"],
                round(entry["score"], 2),
            ])
        except:
            pass
