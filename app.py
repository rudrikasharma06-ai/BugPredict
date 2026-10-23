
"""app.py - Flask dashboard for BugPredict.

Run: python app.py
Then open http://127.0.0.1:5000
"""

import os
import subprocess
import tempfile

from flask import Flask, jsonify, render_template, request

import analyzer
import risk_score

app = Flask(__name__)

DEFAULT_REPO = os.environ.get(
    "BUGPREDICT_REPO",
    "https://github.com/rudrikasharma06-ai/BugPredict-DemoRepo.git",
)

# Temporary directories used for cloned GitHub repositories.
# Keep them available while analysis runs.
CLONED_REPOS = []


def resolve_repo(repo):
    """Return a local repository path, cloning public GitHub URLs if needed."""
    repo = (repo or "").strip()

    if not repo:
        raise ValueError("Please enter a repository path or GitHub URL.")

    if repo.startswith(("https://", "http://", "git@")):
        if repo.startswith("http://"):
            raise ValueError("Please use an HTTPS GitHub URL.")

        repo_dir = tempfile.mkdtemp(prefix="bugpredict_")

        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "20", repo, repo_dir],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "Repository cloning timed out. Try a smaller repository."
            )

        if result.returncode != 0:
            error_message = result.stderr.strip()
            raise RuntimeError(
                "Could not clone repository. Check that the URL is correct "
                "and the repository is public. "
                + error_message[-1000:]
            )

        CLONED_REPOS.append(repo_dir)
        return repo_dir

    if not os.path.isdir(repo):
        raise RuntimeError(f"Repository folder not found: {repo}")

    # Confirm the path is actually a Git repository.
    result = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(f"The folder is not a valid Git repository: {repo}")

    return repo


def run_analysis(repo, base, head):
    """Analyze changes between two commits."""
    local_repo = resolve_repo(repo)

    commits = analyzer.list_commits(local_repo)

    if len(commits) < 2:
        raise RuntimeError(
            "Repository needs at least two commits to compare. "
            "Choose a repository with more commit history."
        )

    # Default to the newest commit and the one immediately before it.
    head = head or commits[0]["hash"]
    base = base or commits[1]["hash"]

    results = risk_score.score_all(
        analyzer.analyze(local_repo, base, head)
    )

    return commits, base, head, results


@app.route("/")
def index():
    repo = request.args.get("repo", DEFAULT_REPO).strip()
    base = request.args.get("base", "").strip()
    head = request.args.get("head", "").strip()

    commits = []
    results = []
    error = None

    try:
        commits, base, head, results = run_analysis(repo, base, head)
    except Exception as exc:
        error = str(exc)

    counts = {
        level: sum(1 for result in results if result.get("level") == level)
        for level in ("High", "Medium", "Low")
    }

    return render_template(
        "index.html",
        repo=repo,
        base=base,
        head=head,
        commits=commits,
        results=results,
        counts=counts,
        error=error,
    )


@app.route("/api/analyze")
def api_analyze():
    """Return repository analysis as JSON."""
    repo = request.args.get("repo", DEFAULT_REPO).strip()
    base = request.args.get("base", "").strip()
    head = request.args.get("head", "").strip()

    try:
        _, base, head, results = run_analysis(repo, base, head)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "repo": repo,
            "base": base,
            "head": head,
            "files": results,
        }
    )


if __name__ == "__main__":
    # Use debug mode locally; disable it in production.
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
    )

