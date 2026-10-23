"""demo_setup.py - builds a small sample Git repository (demo_repo/) for the demo.

It creates several commits over time (including "fix" commits) and finishes
with a deliberately risky change so the dashboard has something to flag.

Run:  python demo_setup.py
"""
import os
import shutil
import subprocess
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_repo")


def git(*args, author="Asha"):
    env = {**os.environ, "GIT_AUTHOR_NAME": author, "GIT_COMMITTER_NAME": author,
           "GIT_AUTHOR_EMAIL": f"{author.lower()}@example.com",
           "GIT_COMMITTER_EMAIL": f"{author.lower()}@example.com"}
    subprocess.run(["git", "-C", REPO, *args], check=True, env=env, capture_output=True)


def write(name, text):
    path = os.path.join(REPO, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def commit(msg, author="Asha"):
    git("add", ".", author=author)
    git("commit", "-m", msg, author=author)


CALC_V1 = '''def add(a, b):
    return a + b


def divide(a, b):
    return a / b
'''

CALC_V2 = '''def add(a, b):
    return a + b


def divide(a, b):
    if b == 0:
        raise ValueError("division by zero")
    return a / b
'''

UTILS_V1 = '''def clean(text):
    return text.strip().lower()
'''

TESTS_V1 = '''from calculator import add

assert add(1, 2) == 3
'''

# Deliberately complex, deeply nested code = the risky change
PAYMENT_V1 = '''def process(order):
    return order["price"] * order["qty"]
'''

PAYMENT_V2 = '''def process(order, user, coupons, region):
    total = 0
    for item in order["items"]:
        if item["qty"] > 0:
            if item["price"] > 0:
                if user["active"] and not user["banned"]:
                    for c in coupons:
                        if c["valid"] and (c["region"] == region or c["region"] == "ALL"):
                            if c["type"] == "percent":
                                total += item["price"] * item["qty"] * (1 - c["value"] / 100)
                            elif c["type"] == "flat":
                                total += max(0, item["price"] * item["qty"] - c["value"])
                            else:
                                total += item["price"] * item["qty"]
                        else:
                            total += item["price"] * item["qty"]
                else:
                    raise PermissionError("user not allowed")
            else:
                raise ValueError("bad price")
        elif item["qty"] < 0:
            raise ValueError("negative qty")
    if region == "EU" and total > 100:
        total *= 1.2
    elif region == "US" and total > 100:
        total *= 1.08
    elif region == "IN" and total > 100:
        total *= 1.18
    while total > 10000:
        total -= 1
    return total
'''


def main():
    if os.path.exists(REPO):
        shutil.rmtree(REPO, onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    os.makedirs(REPO)
    git("init", "-b", "main")

    write("calculator.py", CALC_V1)
    write("utils.py", UTILS_V1)
    write("payment.py", PAYMENT_V1)
    write("test_calculator.py", TESTS_V1)
    commit("Initial project")

    write("calculator.py", CALC_V2)
    commit("Fix divide by zero bug", author="Ravi")

    write("utils.py", UTILS_V1 + "\n\ndef shout(text):\n    return clean(text).upper()\n")
    commit("Add shout helper", author="Meera")

    write("payment.py", PAYMENT_V1.replace("order[\"qty\"]", "order.get(\"qty\", 1)"))
    commit("Fix crash when qty missing", author="Ravi")

    write("payment.py", PAYMENT_V1.replace("order[\"qty\"]", "order.get(\"qty\", 1)") + "\n# tax TODO\n")
    commit("Add tax note", author="Asha")

    write("payment.py", PAYMENT_V1 + "\n# tax TODO\n\ndef tax(x):\n    return x * 0.18\n")
    commit("Fix wrong tax calculation bug", author="Meera")

    write("payment.py", PAYMENT_V1 + "\n\ndef tax(x):\n    return round(x * 0.18, 2)\n")
    commit("Round tax value", author="Asha")

    # The deliberate risky change (HEAD): big rewrite + small edits elsewhere
    write("payment.py", PAYMENT_V2)
    write("calculator.py", CALC_V2 + "\n\ndef power(a, b):\n    if b < 0:\n        return 1 / power(a, -b)\n    return a ** b\n")
    write("utils.py", UTILS_V1 + "\n\ndef shout(text):\n    return clean(text).upper()\n\n\ndef whisper(text):\n    return clean(text) + '...'\n")
    commit("Rewrite payment processing with coupons and regions", author="Meera")

    print(f"Demo repository created at: {REPO}")


if __name__ == "__main__":
    sys.exit(main())
