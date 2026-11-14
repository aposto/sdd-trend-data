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


GH_REPO_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")


def _cand(it, source):
    return {"stars": it["stargazers_count"], "created_at": it["created_at"], "pushed_at": it.get("pushed_at"),
            "description": (it.get("description") or "")[:200], "topics": (it.get("topics") or [])[:10],
            "sources": [source]}


def _add(pool, name, entry, watch):
    if name.lower() in watch:
        return
    if name in pool:
        pool[name]["sources"] = sorted(set(pool[name]["sources"]) | set(entry["sources"]))
        for k, v in entry.items():
            if k != "sources" and v is not None:
                pool[name][k] = v
    else:
        pool[name] = entry


def hn_github_links(cfg, now):
    """Hacker News(Algolia API)에서 최근 N일 키워드 관련 글 중 GitHub 저장소 링크를 모은다."""
    since = int((now - timedelta(days=cfg.get("hn_days", 7))).timestamp())
    found = {}
    for kw in cfg.get("hn_keywords", []):
        url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(
            {"query": kw, "tags": "story", "numericFilters": f"created_at_i>{since}", "hitsPerPage": 50})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "sdd-trend-data"}), timeout=30) as r:
                hits = json.loads(r.read().decode()).get("hits", [])
        except Exception as e:
            print(f"hn search failed for {kw}: {e}", file=sys.stderr)
            continue
        for h in hits:
            text = " ".join(filter(None, [h.get("url"), h.get("story_text")]))
            for owner, repo in GH_REPO_RE.findall(text):
                repo = re.sub(r"\.git$", "", repo)
                if owner.lower() in ("orgs", "topics", "features", "settings", "sponsors", "marketplace"):
                    continue
                name = f"{owner}/{repo}"
                pts = h.get("points") or 0
                if name not in found or pts > found[name]["points"]:
                    found[name] = {"points": pts, "title": (h.get("title") or "")[:120],
                                   "hn_id": h.get("objectID"), "keyword": kw}
    return {k: v for k, v in found.items() if v["points"] >= cfg.get("hn_min_points", 10)}


def discover(cfg, watch, now, prev_pool):
    """넓게 모은다: 키워드·토픽 검색(최근 업데이트, 생성일 무관) + 신생 저장소 검색 + Hacker News 링크.
    이전 스냅샷 후보도 이어서 추적해, 스타 이력으로 주간 증가를 계산할 수 있게 한다."""
    pushed = (now - timedelta(days=cfg["pushed_within_days"])).strftime("%Y-%m-%d")
    young = (now - timedelta(days=cfg["young_within_days"])).strftime("%Y-%m-%d")
    queries = []
    for kw in cfg["keywords"]:
        queries.append((f"{kw} pushed:>={pushed} stars:>={cfg['min_stars']}", f"kw:{kw}"))
        queries.append((f"{kw} created:>={young} stars:>={cfg['young_min_stars']}", f"new:{kw}"))
    for t in cfg["topics"]:
        queries.append((f"topic:{t} pushed:>={pushed} stars:>={cfg['min_stars']}", f"topic:{t}"))
    pool = {}
    for q, src in queries:
        try:
            body = get("/search/repositories", {"q": q, "sort": "stars", "order": "desc", "per_page": cfg["per_query"]})
        except Exception as e:
            print(f"search failed {q}: {e}", file=sys.stderr)
            body = None
        time.sleep(2.5)  # search API: 30 req/min
        for it in (body or {}).get("items", []):
            _add(pool, it["full_name"], _cand(it, src), watch)

    for name, h in hn_github_links(cfg, now).items():
        if name.lower() in watch:
            continue
        info = pool.get(name)
        if info is None:
            try:
                it = get(f"/repos/{name}")
            except Exception:
                it = None
            if not it or it.get("stargazers_count", 0) < cfg["young_min_stars"]:
                continue
            name = it["full_name"]
            _add(pool, name, _cand(it, "hn"), watch)
        else:
            info["sources"] = sorted(set(info["sources"]) | {"hn"})
        if name in pool:
            pool[name]["hn"] = h

    matched_today = set(pool)
    # 이전 후보 중 오늘 검색에 안 걸린 것도 retain_days 동안 계속 추적
    cutoff = now - timedelta(days=cfg["retain_days"])
    for name, old in (prev_pool or {}).items():
        if name in pool or name.lower() in watch:
            continue
        last_seen = old.get("last_matched") or old.get("first_seen")
        if last_seen and datetime.strptime(last_seen, "%Y-%m-%d").replace(tzinfo=timezone.utc) < cutoff:
            continue
        try:
            it = get(f"/repos/{name}")
        except Exception:
            it = None
        if not it:
            continue
        e = _cand(it, "tracked")
        e["sources"] = old.get("sources", ["tracked"])
        if old.get("hn"):
            e["hn"] = old["hn"]
        pool[it["full_name"]] = e

    today = now.strftime("%Y-%m-%d")
    for name, e in pool.items():
        prev = (prev_pool or {}).get(name, {})
        e["first_seen"] = prev.get("first_seen") or today
        e["last_matched"] = today if name in matched_today else prev.get("last_matched", today)
    # 너무 커지지 않게 상한
    if len(pool) > cfg["max_pool"]:
        pool = dict(sorted(pool.items(), key=lambda kv: -kv[1]["stars"])[: cfg["max_pool"]])
    print(f"candidates: {len(pool)}")
    return pool


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
    ap.add_argument("--date", help="스냅샷 파일 날짜(기본: KST 오늘)")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    day = args.date or (now + timedelta(hours=9)).strftime("%Y-%m-%d")  # 파일명은 KST 날짜

    cfg = json.loads((ROOT / "watchlist.json").read_text())
    watch = {r["repo"].lower() for r in cfg["repos"]}

    repos = {}
    for r in cfg["repos"]:
        try:
            repos[r["repo"]] = {"group": r["group"], **repo_metrics(r["repo"], now)}
        except Exception as e:  # 한 저장소 실패가 전체를 막지 않도록
            repos[r["repo"]] = {"group": r["group"], "error": str(e)[:200]}
        print(f"{r['repo']}: {repos[r['repo']].get('stars', repos[r['repo']].get('error'))}")

    prev_eco, prev_pool = {}, {}
    snaps = [p for p in sorted((ROOT / "snapshots").glob("*.json")) if p.stem != day]
    if snaps:
        prev = json.loads(snaps[-1].read_text())
        prev_eco = prev.get("ecosystem_new_repos_by_month", {})
        prev_pool = prev.get("candidates", {})

    snap = {
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "GitHub REST API" + (" (authenticated)" if TOKEN else " (unauthenticated)"),
        "repos": repos,
        "candidates": discover(cfg["discovery"], watch, now, prev_pool),
        "ecosystem_new_repos_by_month": ecosystem_months(cfg["ecosystem_query"], now, prev_eco),
    }
    out = ROOT / "snapshots" / f"{day}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
