"""risk_score.py - turns raw indicators into a 0-100 risk score with reasons.

This is a transparent, rule-based model. Every point of the score can be traced
to a reason shown on the dashboard. NOTE: the score estimates *risk*; it does
not prove that a bug exists.
"""

# Each indicator contributes up to `max` points. Total max = 100.
WEIGHTS = {
    "change_size": 25,    # lines added + deleted in this change
    "complexity": 25,     # cyclomatic complexity of the new file version
    "frequency": 20,      # how often the file was changed before
    "bug_history": 20,    # past commits whose message looks like a bug fix
    "ownership": 5,       # many different authors -> less clear ownership
    "no_tests": 5,        # code changed but no test file touched
}

LOW_MAX = 33
MEDIUM_MAX = 66


def _scale(value, full_at):
    """Map `value` to 0..1, reaching 1 at `full_at`."""
    return max(0.0, min(1.0, value / full_at))


def score_file(f):
    """Return the file dict extended with `score`, `level` and `reasons`."""
    reasons = []
    points = {}

    churn = f["added"] + f["deleted"]
    points["change_size"] = WEIGHTS["change_size"] * _scale(churn, 100)
    if churn >= 100:
        reasons.append(f"Large change: {churn} lines added/deleted")
    elif churn >= 40:
        reasons.append(f"Moderate change size: {churn} lines")

    # nesting makes code harder to reason about, so it adds to the effective complexity
    effective = f["complexity"] + 1.5 * f.get("nesting", 0)
    points["complexity"] = WEIGHTS["complexity"] * _scale(effective, 30)
    if f["complexity"] >= 15:
        reasons.append(f"High complexity (score {f['complexity']})")
    elif f["complexity"] >= 8:
        reasons.append(f"Moderate complexity (score {f['complexity']})")
    if f.get("nesting", 0) >= 4:
        reasons.append(f"Deeply nested code (depth {f['nesting']})")

    points["frequency"] = WEIGHTS["frequency"] * _scale(f["commits"], 8)
    if f["commits"] >= 5:
        reasons.append(f"Frequently modified: {f['commits']} earlier commits")

    points["bug_history"] = WEIGHTS["bug_history"] * _scale(f["fix_commits"], 3)
    if f["fix_commits"] >= 1:
        reasons.append(f"{f['fix_commits']} earlier bug-fix commit(s) touched this file")

    points["ownership"] = WEIGHTS["ownership"] * _scale(f["authors"] - 1, 3)
    if f["authors"] >= 3:
        reasons.append(f"Edited by {f['authors']} different authors")

    points["no_tests"] = 0 if f["tests_in_change"] else WEIGHTS["no_tests"]
    if not f["tests_in_change"] and "test" not in f["path"].lower():
        reasons.append("No test file changed alongside this code")

    if f.get("syntax_error"):
        reasons.append("File does not parse - possible syntax error")
        points["complexity"] = WEIGHTS["complexity"]

    score = round(sum(points.values()))
    level = "Low" if score <= LOW_MAX else "Medium" if score <= MEDIUM_MAX else "High"
    if not reasons:
        reasons.append("No significant risk indicators")

    return {**f, "score": score, "level": level, "reasons": reasons,
            "breakdown": {k: round(v, 1) for k, v in points.items()}}


def score_all(files):
    """Score every file and sort the riskiest first."""
    return sorted((score_file(f) for f in files), key=lambda r: r["score"], reverse=True)
