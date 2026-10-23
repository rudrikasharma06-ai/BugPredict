"""analyzer.py - reads a Git repository and collects raw risk indicators.

Everything here only *measures* things (size of change, complexity, how often
a file changed, how many past "fix" commits touched it). risk_score.py turns
those measurements into a score.
"""
import ast
import subprocess
from collections import Counter

FIX_WORDS = ("fix", "bug", "patch", "hotfix", "error", "crash", "issue")


def git(repo, *args):
    """Run a git command inside `repo` and return its text output."""
    result = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def list_commits(repo, limit=50):
    """Return recent commits as dicts: hash, short hash, message, author."""
    out = git(repo, "log", f"-{limit}", "--pretty=format:%H|%h|%an|%s")
    commits = []
    for line in out.splitlines():
        full, short, author, msg = line.split("|", 3)
        commits.append({"hash": full, "short": short, "author": author, "message": msg})
    return commits


def changed_files(repo, base, head):
    """Files modified between two commits, with lines added / deleted."""
    out = git(repo, "diff", "--numstat", base, head)
    files = []
    for line in out.splitlines():
        added, deleted, path = line.split("\t", 2)
        if added == "-":  # binary file
            continue
        files.append({"path": path, "added": int(added), "deleted": int(deleted)})
    return files


def file_history(repo, path, until):
    """Commit history of one file up to `until`: count, authors, bug-fix count."""
    out = git(repo, "log", until, "--pretty=format:%an|%s", "--", path)
    lines = [l for l in out.splitlines() if l.strip()]
    authors = set()
    fixes = 0
    for l in lines:
        author, _, msg = l.partition("|")
        authors.add(author)
        if any(w in msg.lower() for w in FIX_WORDS):
            fixes += 1
    return {"commits": len(lines), "authors": len(authors), "fix_commits": fixes}


class _Complexity(ast.NodeVisitor):
    """Very small cyclomatic-complexity counter (1 + number of branches)."""

    BRANCHES = (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With,
                ast.BoolOp, ast.IfExp, ast.comprehension, ast.Assert)

    def __init__(self):
        self.score = 1
        self.max_nesting = 0
        self._depth = 0

    def generic_visit(self, node):
        nest = isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With))
        if isinstance(node, self.BRANCHES):
            self.score += len(node.values) - 1 if isinstance(node, ast.BoolOp) else 1
        if nest:
            self._depth += 1
            self.max_nesting = max(self.max_nesting, self._depth)
        super().generic_visit(node)
        if nest:
            self._depth -= 1


def complexity_of(repo, path, rev):
    """Cyclomatic complexity + nesting depth of a Python file at revision `rev`.

    Non-Python files fall back to a rough keyword count so the tool still works.
    """
    try:
        source = git(repo, "show", f"{rev}:{path}")
    except RuntimeError:  # file deleted in `rev`
        return {"complexity": 0, "nesting": 0, "loc": 0}
    loc = len([l for l in source.splitlines() if l.strip()])
    if path.endswith(".py"):
        try:
            visitor = _Complexity()
            visitor.visit(ast.parse(source))
            return {"complexity": visitor.score, "nesting": visitor.max_nesting, "loc": loc}
        except SyntaxError:
            return {"complexity": 0, "nesting": 0, "loc": loc, "syntax_error": True}
    keywords = ("if ", "for ", "while ", "case ", "catch", "&&", "||", "?")
    score = 1 + sum(source.count(k) for k in keywords)
    return {"complexity": score, "nesting": 0, "loc": loc}


def has_test_change(files):
    """True if the change set touches at least one test file."""
    return any("test" in f["path"].lower() for f in files)


def analyze(repo, base, head):
    """Collect every indicator for every file changed between base and head."""
    files = changed_files(repo, base, head)
    test_touched = has_test_change(files)
    results = []
    for f in files:
        hist = file_history(repo, f["path"], base)   # history BEFORE this change
        comp = complexity_of(repo, f["path"], head)
        results.append({**f, **hist, **comp, "tests_in_change": test_touched})
    return results


def author_summary(repo, limit=200):
    """Commits per author (used for the small chart on the dashboard)."""
    out = git(repo, "log", f"-{limit}", "--pretty=format:%an")
    return dict(Counter(out.splitlines()))
