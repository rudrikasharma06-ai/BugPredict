"""app.py - Flask dashboard for BugPredict.

Run:  python app.py        then open http://127.0.0.1:5000
"""
import os

from flask import Flask, jsonify, render_template, request

import analyzer
import risk_score

app = Flask(__name__)

DEFAULT_REPO = os.environ.get(
    "BUGPREDICT_REPO", os.path.join(os.path.dirname(__file__), "demo_repo")
)


def run_analysis(repo, base, head):
    commits = analyzer.list_commits(repo)
    if len(commits) < 2:
        raise RuntimeError("Repository needs at least two commits to compare.")
    head = head or commits[0]["hash"]       # newest commit
    base = base or commits[1]["hash"]       # the one before it
    scored = risk_score.score_all(analyzer.analyze(repo, base, head))
    return commits, base, head, scored


@app.route("/")
def index():
    repo = request.args.get("repo", DEFAULT_REPO)
    base = request.args.get("base", "")
    head = request.args.get("head", "")
    try:
        commits, base, head, results = run_analysis(repo, base, head)
        error = None
    except Exception as exc:  # show friendly message instead of a stack trace
        commits, results, error = [], [], str(exc)
    counts = {lvl: sum(1 for r in results if r["level"] == lvl) for lvl in ("High", "Medium", "Low")}
    return render_template("index.html", repo=repo, base=base, head=head,
                           commits=commits, results=results, counts=counts, error=error)


@app.route("/api/analyze")
def api_analyze():
    """JSON version of the same analysis (handy for demos and testing)."""
    repo = request.args.get("repo", DEFAULT_REPO)
    try:
        _, base, head, results = run_analysis(repo, request.args.get("base", ""), request.args.get("head", ""))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"repo": repo, "base": base, "head": head, "files": results})


if __name__ == "__main__":
    app.run(debug=True)
