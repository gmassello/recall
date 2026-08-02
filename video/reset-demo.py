#!/usr/bin/env python3
"""
reset-demo.py — put the deployed demo back into the exact state a take needs.

Run it with the backend venv, from anywhere:

    cd ~/Documents/recall
    backend/.venv/bin/python video/reset-demo.py            # reset + verify
    backend/.venv/bin/python video/reset-demo.py --check    # verify only, change nothing

Idempotent. Safe to run twice. It never touches the 25 seed incidents.

What it does, in the order the runbook lays out:
  1. memory  -> delete every incident whose source is not "seed" (the postmortems
                a take leaves behind), leaving 25 seed rows
  2. quality -> "Reboot loop after an update: current procedure" back to 0.10, and
                "Everything slow because of browser adware" back to 0.0 / 0 helpful.
                This is the tuning that decides whether the ticket-2 beat works:
                above ~0.34 the current procedure outranks the fresh postmortem and
                the beat silently fails.
  3. tickets -> delete ticket 1 (it is created on camera), then delete and recreate
                tickets 2 and 3 so neither carries a saved diagnosis. Deleting a
                ticket cascades its diagnosis; recreating is the only clean way.

API base and demo key are read from the deployed JS bundle, which is where the
build bakes them (deploy.sh: VITE_API_BASE / VITE_DEMO_API_KEY). DATABASE_URL comes
from backend/.env.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

SITE = "https://d2n13wfb8jv9v.cloudfront.net"
REPO = Path(__file__).resolve().parent.parent

CURRENT_PROCEDURE = "Reboot loop after an update: current procedure"
ADWARE = "Everything slow because of browser adware"

TICKET_1_TITLE = "PC restarts over and over after last night's Windows update"

TICKET_2 = {
    "title": "Another PC in an endless restart loop after the same update",
    "description": "Boots to the logo and restarts, over and over. Same as the one we fixed earlier today.",
    "service": "software-pc",
    "severity": "high",
}
TICKET_3 = {
    "title": "Android app keeps closing right after the latest OS update",
    "description": "Since updating the phone OS, the banking app closes by itself a few seconds after opening. Reinstalling did not help.",
    "service": "software-phone",
    "severity": "medium",
}

CHECK_ONLY = "--check" in sys.argv
ctx = ssl.create_default_context()

ok = "\033[32m✓\033[0m"
bad = "\033[31m✗\033[0m"
dim = "\033[2m%s\033[0m"


def http(method: str, url: str, key: str = "", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if key:
        req.add_header("X-API-Key", key)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def discover() -> tuple[str, str]:
    """Pull the API base and demo key out of the deployed bundle."""
    with urllib.request.urlopen(SITE + "/", context=ctx, timeout=30) as r:
        html = r.read().decode()
    m = re.search(r"/assets/index-[^\"]+\.js", html)
    if not m:
        sys.exit(f"{bad} could not find the JS bundle in the page — is the site up?")
    with urllib.request.urlopen(SITE + m.group(0), context=ctx, timeout=30) as r:
        js = r.read().decode()

    api = None
    # the bundle has carried two shapes: '"X-API-Key":VAR' (object literal, pre-B27)
    # and 'set("X-API-Key",VAR)' (Headers.set, current)
    key = ""
    a = re.search(r'set\("X-API-Key",([A-Za-z_$][\w$]*)\)', js) or re.search(
        r'"X-API-Key":([A-Za-z_$][\w$]*)', js
    )
    if a:
        v = re.search(re.escape(a.group(1)) + r'="([^"]*)"', js)
        key = v.group(1) if v else ""
    if not key:
        v = re.search(r'set\("X-API-Key","([^"]*)"\)', js) or re.search(
            r'"X-API-Key":"([^"]*)"', js
        )
        key = v.group(1) if v else ""
    u = re.search(r"https://[a-z0-9]+\.lambda-url\.[a-z0-9-]+\.on\.aws", js)
    if u:
        api = u.group(0).rstrip("/")
    if not api:
        sys.exit(f"{bad} could not find the API base in the bundle.")
    if not key:
        print(f"  {dim % 'no demo key in the bundle; protected calls may 401'}")
    return api, key


def database_url() -> str:
    env = REPO / "backend" / ".env"
    if not env.exists():
        sys.exit(f"{bad} {env} not found — needed for the quality tuning step.")
    m = re.search(r"^DATABASE_URL=(.*)$", env.read_text(), re.M)
    if not m:
        sys.exit(f"{bad} DATABASE_URL is not set in backend/.env")
    return m.group(1).strip().strip("\"'")


def tune_quality() -> None:
    try:
        import psycopg
    except ImportError:
        sys.exit(f"{bad} psycopg not importable — run this with backend/.venv/bin/python")
    with psycopg.connect(database_url()) as conn:
        conn.execute("UPDATE incidents SET quality_score = 0.1 WHERE title = %s", (CURRENT_PROCEDURE,))
        conn.execute(
            "UPDATE incidents SET quality_score = 0.0, times_helpful = 0 WHERE title = %s", (ADWARE,)
        )
    print(f"  {ok} quality tuned: current procedure 0.10, adware 0.0 / 0 helpful")


def main() -> int:
    print(f"\n  {SITE}")
    api, key = discover()
    print(f"  {dim % api}\n")

    # ---- 1. memory ---------------------------------------------------------
    _, memory = http("GET", f"{api}/memory", key)
    if memory is None:
        sys.exit(f"{bad} GET /memory failed — is the Lambda healthy?")
    strays = [i for i in memory if i.get("source") != "seed"]
    if CHECK_ONLY:
        print(f"  {'' if not strays else bad} memory: {len(memory)} rows, {len(strays)} non-seed")
    else:
        for i in strays:
            code, _ = http("DELETE", f"{api}/memory/{i['id']}", key)
            print(f"  {ok if code in (204, 200) else bad} deleted postmortem {dim % i['title'][:52]}")
        if not strays:
            print(f"  {ok} memory already clean")

    # ---- 2. quality --------------------------------------------------------
    if not CHECK_ONLY:
        tune_quality()

    # ---- 3. tickets --------------------------------------------------------
    # GET /tickets hides resolved ones, and a finished take leaves ticket 1
    # resolved — sweep both.
    _, open_tickets = http("GET", f"{api}/tickets", key)
    _, resolved_tickets = http("GET", f"{api}/tickets?status=resolved", key)
    all_tickets = (open_tickets or []) + (resolved_tickets or [])
    doomed = [
        t
        for t in all_tickets
        if t["title"] in (TICKET_1_TITLE, TICKET_2["title"], TICKET_3["title"])
    ]
    if not CHECK_ONLY:
        for t in doomed:
            code, _ = http("DELETE", f"{api}/tickets/{t['id']}", key)
            print(f"  {ok if code in (204, 200) else bad} deleted ticket {dim % t['title'][:52]}")
        for spec in (TICKET_2, TICKET_3):
            code, made = http("POST", f"{api}/tickets", key, spec)
            print(f"  {ok if code == 201 else bad} created  ticket {dim % spec['title'][:52]}")

    # ---- verify ------------------------------------------------------------
    print("\n  verifying\n")
    problems = 0

    _, memory = http("GET", f"{api}/memory", key)
    memory = memory or []
    seed_only = all(i.get("source") == "seed" for i in memory)
    good = len(memory) == 25 and seed_only
    problems += not good
    print(f"  {ok if good else bad} memory: {len(memory)} rows, all seed = {seed_only}")

    by_title = {i["title"]: i for i in memory}
    cp = by_title.get(CURRENT_PROCEDURE)
    good = cp is not None and abs(cp["quality_score"] - 0.1) < 1e-6 and cp["validity"] == "current"
    problems += not good
    print(
        f"  {ok if good else bad} current procedure: quality "
        f"{cp['quality_score'] if cp else '?'}, validity {cp['validity'] if cp else '?'}"
    )

    stale = by_title.get("Windows reboot loop after an update")
    good = stale is not None and stale["validity"] == "superseded"
    problems += not good
    print(f"  {ok if good else bad} stale procedure: validity {stale['validity'] if stale else '?'}")

    _, open_tickets = http("GET", f"{api}/tickets", key)
    _, resolved_tickets = http("GET", f"{api}/tickets?status=resolved", key)
    all_tickets = (open_tickets or []) + (resolved_tickets or [])
    titles = {t["title"]: t for t in all_tickets}

    good = TICKET_1_TITLE not in titles
    problems += not good
    print(f"  {ok if good else bad} ticket 1 absent (it is typed on camera)")

    for label, spec in (("ticket 2", TICKET_2), ("ticket 3", TICKET_3)):
        t = titles.get(spec["title"])
        if t is None:
            problems += 1
            print(f"  {bad} {label} missing")
            continue
        code, _ = http("GET", f"{api}/tickets/{t['id']}/diagnosis", key)
        clean = code == 404 and t["status"] == "open"
        problems += not clean
        print(
            f"  {ok if clean else bad} {label}: status {t['status']}, "
            f"saved diagnosis = {'no' if code == 404 else 'YES — not clean'}"
        )

    if problems:
        print(f"\n  {bad} {problems} problem(s). Do not record until these are green.\n")
        return 1
    print(f"\n  {ok} demo is ready to record.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
