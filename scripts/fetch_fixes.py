"""For closed issues, find the merged PR that closed them and the files it changed.

Usage: python scripts/fetch_fixes.py scikit-learn/scikit-learn --issues data/sklearn_issues.jsonl \
           --out data/sklearn_fixes.jsonl

Read-only GitHub GraphQL queries (needs your `gh` login for the token).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import httpx

BATCH = 20


def gh_token() -> str:
    out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def build_query(owner: str, name: str, numbers: list[int]) -> str:
    parts = []
    for n in numbers:
        parts.append(
            f"i{n}: issue(number: {n}) {{ number state closedByPullRequestsReferences(first: 3) "
            f"{{ nodes {{ number merged files(first: 100) {{ nodes {{ path }} }} }} }} }}"
        )
    return f'query {{ repository(owner: "{owner}", name: "{name}") {{ {" ".join(parts)} }} }}'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--issues", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    owner, name = a.repo.split("/")

    numbers = [
        json.loads(line)["number"]
        for line in Path(a.issues).read_text(encoding="utf-8").splitlines()
        if json.loads(line)["state"] == "closed"
    ]
    headers = {"Authorization": f"Bearer {gh_token()}"}
    found = 0
    with httpx.Client(headers=headers, timeout=60) as c, open(a.out, "w", encoding="utf-8") as f:
        for i in range(0, len(numbers), BATCH):
            chunk = numbers[i : i + BATCH]
            r = c.post("https://api.github.com/graphql", json={"query": build_query(owner, name, chunk)})
            r.raise_for_status()
            data = r.json()
            if "errors" in data and not data.get("data"):
                raise SystemExit(str(data["errors"])[:500])
            for node in (data["data"]["repository"] or {}).values():
                if not node:
                    continue
                prs = [p for p in node["closedByPullRequestsReferences"]["nodes"] if p["merged"]]
                if not prs:
                    continue
                files = sorted({fn["path"] for p in prs for fn in p["files"]["nodes"]})
                f.write(json.dumps({
                    "number": node["number"],
                    "prs": [p["number"] for p in prs],
                    "files": files,
                }) + "\n")
                found += 1
    print(f"{found} of {len(numbers)} closed issues have a merged fixing PR", file=sys.stderr)


if __name__ == "__main__":
    main()
