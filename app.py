"""app.py - Flask dashboard for BugPredict.

Run: python app.py
Then open http://127.0.0.1:5000
"""

import os
import shutil
import subprocess
import tempfile

from flask import Flask, jsonify, render_template, request

import analyzer
import risk_score

app = Flask(__name__)

DEFAULT_REPO = os.environ.get("BUGPREDICT_REPO", "").strip()


@app.after_request
def add_cors_headers(response):
    """Enable CORS so external or cross-origin consumers can access API endpoints."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def resolve_repo(repo):
    """Resolve a repository path or URL.

    - Returns (local_repo_path, is_temp, repo_display_name).
    - Public GitHub repositories are cloned into a temporary folder.
    - Local directory paths are verified as valid Git repositories.
    - Temporary folders are guaranteed to be cleaned up after analysis.
    """
    repo = (repo or "").strip()

    if not repo:
        raise ValueError(
            "Please enter a GitHub repository URL (e.g. https://github.com/owner/repository)."
        )

    # Insecure HTTP URL check
    if repo.startswith("http://"):
        raise ValueError(
            "Insecure HTTP URLs are not supported. Please use HTTPS "
            "(e.g. https://github.com/owner/repository)."
        )

    # Remote GitHub or Git URL
    if repo.startswith(("https://", "git@")):
        clean_url = repo.rstrip("/")
        display_name = clean_url.split("/")[-1].replace(".git", "")

        repo_dir = tempfile.mkdtemp(prefix="bugpredict_")
        try:
            result = subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth=100",
                    "--no-single-branch",
                    clean_url,
                    repo_dir,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            shutil.rmtree(repo_dir, ignore_errors=True)
            raise RuntimeError(
                "Repository cloning timed out after 120 seconds. "
                "The repository may be very large or GitHub is experiencing latency."
            )
        except Exception as exc:
            shutil.rmtree(repo_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to clone repository: {str(exc)}")

        if result.returncode != 0:
            shutil.rmtree(repo_dir, ignore_errors=True)
            stderr = result.stderr.strip().lower()
            if "not found" in stderr or "repository" in stderr or "authentication" in stderr:
                raise RuntimeError(
                    f"Repository not found or is private: '{repo}'. "
                    "Please check the URL and ensure the repository is public."
                )
            raise RuntimeError(f"Could not clone repository: {result.stderr.strip()[-500:]}")

        return repo_dir, True, display_name

    # Local filesystem path
    if os.path.isdir(repo):
        result = subprocess.run(
            ["git", "-C", repo, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            display_name = os.path.basename(os.path.abspath(repo))
            return repo, False, display_name
        raise RuntimeError(f"The folder '{repo}' is not a valid Git repository.")

    raise RuntimeError(
        f"Repository folder not found: '{repo}'. "
        "If this is a GitHub repository, please enter a complete URL like 'https://github.com/owner/repository'."
    )


def resolve_commit_ref(local_repo, ref, label="commit", repo_display=""):
    """Verify that a commit reference exists inside local_repo and resolve its full 40-character SHA1 hash.

    Accepts full hashes, short hashes, branch names, tags, etc.
    """
    ref = (ref or "").strip()
    if not ref:
        return ""

    res = subprocess.run(
        ["git", "-C", local_repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()

    # If not found immediately, check if it's a shallow clone and try fetching deeper
    shallow_check = subprocess.run(
        ["git", "-C", local_repo, "rev-parse", "--is-shallow-repository"],
        capture_output=True,
        text=True,
        check=False,
    )
    if shallow_check.stdout.strip() == "true":
        subprocess.run(
            ["git", "-C", local_repo, "fetch", "--depth=500"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        res_retry = subprocess.run(
            ["git", "-C", local_repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res_retry.returncode == 0 and res_retry.stdout.strip():
            return res_retry.stdout.strip()

    repo_info = f" in repository '{repo_display}'" if repo_display else ""
    raise RuntimeError(
        f"Commit '{ref}' ({label}) was not found{repo_info}. "
        "Please verify that the commit hash belongs to this repository and is entered correctly."
    )


def run_analysis(repo, base="", head="", author=""):
    """Clone or inspect repository, validate commits, execute risk analysis, and return structured results."""
    local_repo, is_temp, repo_display = resolve_repo(repo)

    try:
        commits = analyzer.list_commits(local_repo, limit=100)

        if len(commits) == 0:
            raise RuntimeError(
                f"Repository '{repo_display}' is empty (has no commit history)."
            )

        if len(commits) == 1:
            raise RuntimeError(
                f"Repository has only 1 commit ({commits[0]['short']}: '{commits[0]['message']}'). "
                "BugPredict requires at least two commits to calculate a change diff."
            )

        # Resolve Head commit
        head = (head or "").strip()
        if not head:
            head = commits[0]["hash"]
        else:
            head = resolve_commit_ref(local_repo, head, "head", repo_display)

        # Resolve Base commit
        base = (base or "").strip()
        if not base:
            # Default to parent commit of head, or the commit immediately prior in log
            if head == commits[0]["hash"]:
                base = commits[1]["hash"]
            else:
                head_idx = next((i for i, c in enumerate(commits) if c["hash"] == head), -1)
                if head_idx != -1 and head_idx + 1 < len(commits):
                    base = commits[head_idx + 1]["hash"]
                else:
                    base = commits[0]["hash"] if commits[0]["hash"] != head else commits[1]["hash"]
        else:
            base = resolve_commit_ref(local_repo, base, "base", repo_display)

        if base == head:
            raise RuntimeError(
                f"Base commit and Head commit are identical ({base[:7]}). "
                "Please select two different commits to calculate a change diff."
            )

        # Retrieve unique authors from repository history
        authors = analyzer.list_authors(local_repo)

        # Run analysis (with optional author filter)
        results = risk_score.score_all(
            analyzer.analyze(local_repo, base, head, author=author)
        )

        return commits, base, head, results, authors, repo_display
    finally:
        if is_temp:
            shutil.rmtree(local_repo, ignore_errors=True)


@app.route("/")
def index():
    repo = request.args.get("repo", DEFAULT_REPO).strip()
    base = request.args.get("base", "").strip()
    head = request.args.get("head", "").strip()
    author = request.args.get("author", "").strip()

    commits = []
    results = []
    authors = []
    repo_display = ""
    error = None

    if repo:
        try:
            commits, base, head, results, authors, repo_display = run_analysis(
                repo, base, head, author=author
            )
        except Exception as exc:
            error = str(exc)

    counts = {
        level: sum(1 for result in results if result.get("level") == level)
        for level in ("High", "Medium", "Low")
    }

    return render_template(
        "index.html",
        repo=repo,
        repo_display=repo_display or (repo.split("/")[-1].replace(".git", "") if repo else ""),
        base=base,
        head=head,
        author=author,
        commits=commits,
        authors=authors,
        results=results,
        counts=counts,
        error=error,
    )


@app.route("/api/analyze")
def api_analyze():
    """Execute repository diff risk analysis and return results as JSON.

    Query parameters:
    - repo: GitHub repository HTTPS URL or local repository path.
    - base: Base commit hash (older, optional).
    - head: Head commit hash (newer, optional).
    - author: Contributor / author name or email filter (optional).
    """
    repo = request.args.get("repo", DEFAULT_REPO).strip()
    base = request.args.get("base", "").strip()
    head = request.args.get("head", "").strip()
    author = request.args.get("author", "").strip()

    if not repo:
        return (
            jsonify(
                {
                    "error": "No repository URL provided. Please provide a GitHub URL (e.g. ?repo=https://github.com/owner/repository)."
                }
            ),
            400,
        )

    try:
        commits, base, head, results, authors, repo_display = run_analysis(
            repo, base, head, author=author
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    counts = {
        level: sum(1 for result in results if result.get("level") == level)
        for level in ("High", "Medium", "Low")
    }

    return jsonify(
        {
            "repo": repo,
            "repo_display": repo_display,
            "base": base,
            "head": head,
            "author": author,
            "commits": commits[:30],
            "authors": authors,
            "files": results,
            "counts": counts,
            "total_files": len(results),
        }
    )


@app.route("/api/commits")
def api_commits():
    """Retrieve recent commits and contributors for a given repository."""
    repo = request.args.get("repo", "").strip()
    if not repo:
        return jsonify({"error": "No repository URL provided."}), 400

    local_repo, is_temp, repo_display = None, False, ""
    try:
        local_repo, is_temp, repo_display = resolve_repo(repo)
        commits = analyzer.list_commits(local_repo, limit=30)
        authors = analyzer.list_authors(local_repo)
        return jsonify(
            {
                "repo": repo,
                "repo_display": repo_display,
                "commits": commits,
                "authors": authors,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        if is_temp and local_repo:
            shutil.rmtree(local_repo, ignore_errors=True)


if __name__ == "__main__":
    # Bind to 0.0.0.0 so Render and cloud deployments can receive external traffic.
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
    )
