#!/usr/bin/env python3
"""관심 목록 저장소의 GitHub 지표를 수집해 snapshots/YYYY-MM-DD.json 으로 저장한다.

표준 라이브러리만 사용한다. GITHUB_TOKEN 환경변수가 있으면 인증 호출(시간당 5,000회, Actions 토큰은 1,000회).

사용:  python3 scripts/collect.py [--date YYYY-MM-DD]
"""
import argparse
import calendar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def get(path, params=None, raw=False):
    url = path if path.startswith("http") else API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sdd-trend-data",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode() or "null")
                return (body, dict(r.headers)) if raw else body
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return (None, {}) if raw else None
            if e.code in (403, 429) and attempt < 3:
                reset = int(e.headers.get("x-ratelimit-reset", "0") or 0)
                wait = max(5, min(90, reset - int(time.time()))) if reset else 20 * (attempt + 1)
                print(f"rate limited on {url}, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if e.code >= 500 and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            if attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def count_commits_since(repo, since_iso):
    body, headers = get(f"/repos/{repo}/commits", {"since": since_iso, "per_page": 1}, raw=True)
    if body is None:
        return None
    link = headers.get("Link") or headers.get("link") or ""
    m = re.search(r'[?&]page=(\d+)>; rel="last"', link)
    return int(m.group(1)) if m else len(body)


def repo_metrics(repo, now):
    info = get(f"/repos/{repo}")
    if info is None:
        return {"error": "not_found"}
    rel = get(f"/repos/{repo}/releases/latest")
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "full_name": info["full_name"],
        "stars": info["stargazers_count"],
        "forks": info["forks_count"],
        "open_issues": info["open_issues_count"],
        "created_at": info["created_at"],
        "pushed_at": info["pushed_at"],
        "archived": info.get("archived", False),
        "description": (info.get("description") or "")[:200],
        "latest_release": ({"tag": rel.get("tag_name"), "published_at": rel.get("published_at")} if rel else None),
        "commits_7d": count_commits_since(repo, week_ago),
    }


def search_count(q):
    body = get("/search/repositories", {"q": q, "per_page": 1})
    time.sleep(2.5)  # search API: 30 req/min
    return body["total_count"] if body else None


def discover(cfg, watch, now):
    since = (now - timedelta(days=cfg["created_within_days"])).strftime("%Y-%m-%d")
    seen = {}
    for kw in cfg["keywords"]:
        q = f"{kw} created:>={since} stars:>={cfg['min_stars']}"
        body = get("/search/repositories", {"q": q, "sort": "stars", "order": "desc", "per_page": 30})
        time.sleep(2.5)
        for it in (body or {}).get("items", []):
            name = it["full_name"]
            if name.lower() in watch or name in seen:
                continue
            seen[name] = {"stars": it["stargazers_count"], "created_at": it["created_at"],
                          "description": (it.get("description") or "")[:200], "matched": kw}
    return seen


def ecosystem_months(query, now, existing):
    """지난 완결 월들의 '키워드 포함 신규 저장소 수'. 이미 기록된 달은 다시 조회하지 않는다."""
    out = dict(existing)
    y, m = now.year, now.month
    for _ in range(3):  # 최근 3개 완결 월만 보강
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        key = f"{y:04d}-{m:02d}"
        if key in out:
            continue
        last = calendar.monthrange(y, m)[1]
        out[key] = search_count(f"{query} created:{key}-01..{key}-{last:02d}")
    return dict(sorted(out.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="스냅샷 파일 날짜(기본: UTC 오늘)")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    day = args.date or now.strftime("%Y-%m-%d")

    cfg = json.loads((ROOT / "watchlist.json").read_text())
    watch = {r["repo"].lower() for r in cfg["repos"]}

    repos = {}
    for r in cfg["repos"]:
        try:
            repos[r["repo"]] = {"group": r["group"], **repo_metrics(r["repo"], now)}
        except Exception as e:  # 한 저장소 실패가 전체를 막지 않도록
            repos[r["repo"]] = {"group": r["group"], "error": str(e)[:200]}
        print(f"{r['repo']}: {repos[r['repo']].get('stars', repos[r['repo']].get('error'))}")

    prev_eco = {}
    snaps = sorted((ROOT / "snapshots").glob("*.json"))
    if snaps:
        prev_eco = json.loads(snaps[-1].read_text()).get("ecosystem_new_repos_by_month", {})

    snap = {
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "GitHub REST API" + (" (authenticated)" if TOKEN else " (unauthenticated)"),
        "repos": repos,
        "candidates": discover(cfg["discovery"], watch, now),
        "ecosystem_new_repos_by_month": ecosystem_months(cfg["ecosystem_query"], now, prev_eco),
    }
    out = ROOT / "snapshots" / f"{day}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
