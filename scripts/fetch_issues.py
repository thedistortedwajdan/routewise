"""Download real issues (with maintainer-applied labels) from a public GitHub repo.

Usage: python scripts/fetch_issues.py scikit-learn/scikit-learn --pages 20 --out data/sklearn_issues.jsonl

Read-only. Uses your `gh` login token if available (higher rate limit), else unauthenticated.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import httpx


def gh_token() -> str | None:
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--out", default="data/issues.jsonl")
    a = ap.parse_args()

    headers = {"Accept": "application/vnd.github+json"}
    if tok := gh_token():
        headers["Authorization"] = f"Bearer {tok}"

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with httpx.Client(headers=headers, timeout=30) as c, out.open("w", encoding="utf-8") as f:
        for page in range(1, a.pages + 1):
            r = c.get(
                f"https://api.github.com/repos/{a.repo}/issues",
                params={"state": "all", "per_page": 100, "page": page,
                        "sort": "created", "direction": "desc"},
            )
            r.raise_for_status()
            items = r.json()
            if not items:
                break
            for it in items:
                if "pull_request" in it:
                    continue
                f.write(json.dumps({
                    "number": it["number"],
                    "title": it["title"],
                    "body": it.get("body") or "",
                    "labels": [lb["name"] for lb in it["labels"]],
                    "created_at": it["created_at"],
                    "state": it["state"],
                    "comments": it["comments"],
                }, ensure_ascii=False) + "\n")
                n += 1
    print(f"wrote {n} issues to {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
