# BugPredict - Early Bug Risk Detection System

BugPredict reads a Git repository, compares two commits and gives every changed
file a **risk score (0-100)** with plain-English reasons. A Flask dashboard shows
which files deserve extra review or testing.

> BugPredict estimates risk. It does not prove that a bug exists.

## How it works

| Indicator | Max points | What it measures |
|---|---|---|
| Change size | 25 | Lines added + deleted between the two commits |
| Complexity | 25 | Cyclomatic complexity and nesting depth of the new file |
| Change frequency | 20 | How many earlier commits touched the file |
| Bug-fix history | 20 | Earlier commits with "fix / bug / crash..." in the message |
| Ownership | 5 | Number of different authors |
| Missing tests | 5 | Code changed but no test file changed |

Levels: **Low** 0-33, **Medium** 34-66, **High** 67-100.

## Files

```
BugPredict/
├── app.py            Flask dashboard + /api/analyze JSON endpoint
├── analyzer.py       Reads Git history, measures indicators
├── risk_score.py     Combines indicators into a score + reasons
├── demo_setup.py     Builds a sample repo for the demo
├── templates/index.html
├── static/style.css
└── requirements.txt
```

## Run it (Windows, VS Code terminal)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python demo_setup.py
python app.py
```

Open http://127.0.0.1:5000 . By default it compares the two newest commits of
`demo_repo`. To analyze your own project:

```
set BUGPREDICT_REPO=C:\path\to\your\repo
python app.py
```

(or type the path into the dashboard's "Repository path" box).

## Push to GitHub

```
git init
git add .
git commit -m "Initial BugPredict project"
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git branch -M main
git push -u origin main
```

## Ideas for extension

- Train a classifier (scikit-learn) on real bug-fix history instead of fixed weights.
- Pull pull-request data from the GitHub API.
- Support more languages with `radon`, `pylint` or `eslint`.
