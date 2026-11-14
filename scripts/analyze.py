#!/usr/bin/env python3
"""스냅샷 이력으로 주간 리포트용 지표를 계산한다.

출력: reports/YYYY-MM-DD.json (기계용), reports/YYYY-MM-DD.md (게시판 붙여넣기용 표)

지표
- 일평균(전체)      = 현재 스타 ÷ 생성 후 경과일
- 일평균(최근 30일) = (현재 − 약 30일 전 값) ÷ 실제 경과일   (스냅샷이 없으면 baselines/ 사용)
- 주간 증가(7일)    = 현재 − 약 7일 전 값, 일평균은 실제 경과일로 나눔
- 추세              = 일평균(30일) ÷ 일평균(전체)  → ≥1.2 가속, <0.8 둔화, 그 사이 유지

사용:  python3 scripts/analyze.py [--date YYYY-MM-DD]
"""
import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUP_KO = {"spec": "스펙 프레임워크", "loop": "실행 루프·생명주기", "skills": "스킬·방법론", "candidate": "관찰 후보"}
WINDOWS = {"7d": (7, 3), "30d": (30, 10)}  # (목표 일수, 허용 오차 일수)


def ts(s):
    return datetime.strptime(s.replace("Z", ""), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def load_series():
    """repo(소문자) -> [(datetime, stars)]"""
    series, snaps = {}, []
    for p in sorted((ROOT / "snapshots").glob("*.json")):
        s = json.loads(p.read_text())
        s["_file"] = p.stem
        snaps.append(s)
        t = ts(s["as_of"])
        for name, r in s["repos"].items():
            if "stars" in r:
                series.setdefault(name.lower(), []).append((t, r["stars"]))
    for p in sorted((ROOT / "baselines").glob("*.json")):
        b = json.loads(p.read_text())
        for name, v in b.get("stars", {}).items():
            if v:
                series.setdefault(name.lower(), []).append((ts(v[0]), v[1]))
    for k in series:
        series[k].sort()
    return series, snaps


def value_near(points, target, tol_days):
    best = None
    for t, v in points:
        d = abs((t - target).total_seconds()) / 86400
        if d <= tol_days and (best is None or d < best[0]):
            best = (d, t, v)
    return best and (best[1], best[2])


def fmt(n, digits=0):
    if n is None:
        return "—"
    return f"{n:,.{digits}f}"


def trend_label(ratio):
    if ratio is None:
        return "—"
    word = "가속" if ratio >= 1.2 else ("둔화" if ratio < 0.8 else "유지")
    return f"{word} ({ratio:.2f})"


def rank_candidates(snaps, cur, now, relevance):
    """후보 풀에서 급상승·신생 고성장·HN 화제 신호가 있는 저장소를 고른다."""
    hist = {}
    for sn in snaps:
        t = ts(sn["as_of"])
        if t > now:
            continue
        for n, c in (sn.get("candidates") or {}).items():
            hist.setdefault(n, []).append((t, c["stars"]))
    out = []
    for n, c in (cur.get("candidates") or {}).items():
        age = max(1.0, (now - ts(c["created_at"])).total_seconds() / 86400)
        avg_life = c["stars"] / age
        hit = value_near(hist.get(n, []), now - timedelta(days=7), 3)
        d7 = None
        if hit and hit[0] < now:
            d7 = c["stars"] - hit[1]
        text = " ".join([n.split("/")[-1].replace("-", " "), c.get("description", ""), " ".join(c.get("topics", []))]).lower()
        if re.search(relevance["strong"], text):
            tier = "핵심"
        elif re.search(relevance["weak"], text):
            tier = "주변"
        else:
            continue
        signals = []
        if d7 is not None and (d7 >= 300 or (d7 >= 100 and d7 / 7 >= 2 * avg_life)):
            signals.append(f"급상승 +{d7:,}/주")
        if age <= 120 and avg_life >= 15:
            signals.append(f"신생 고성장 {avg_life:,.0f}/일")
        hn = c.get("hn")
        if hn and hn.get("points", 0) >= 50:
            signals.append(f"HN {hn['points']}점")
        if not signals:
            continue
        score = (d7 if d7 is not None else avg_life * 7) + (hn or {}).get("points", 0) * 5
        out.append({"repo": n, "relevance": tier, "stars": c["stars"], "delta_7d": d7, "avg_life": avg_life,
                    "created": c["created_at"][:10], "first_seen": c.get("first_seen"),
                    "signals": signals, "sources": c.get("sources"), "hn": hn,
                    "description": c.get("description", ""), "topics": c.get("topics", []), "score": score})
    out.sort(key=lambda r: (r["relevance"] != "핵심", -r["score"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="기준 스냅샷 날짜(기본: 최신)")
    args = ap.parse_args()

    series, snaps = load_series()
    if not snaps:
        raise SystemExit("snapshots/ 가 비어 있습니다")
    cur = next((s for s in snaps if s["_file"] == args.date), snaps[-1]) if args.date else snaps[-1]
    now = ts(cur["as_of"])
    prev7 = value_near  # alias for readability

    rows = []
    for name, r in cur["repos"].items():
        if "stars" not in r:
            rows.append({"repo": name, "group": r.get("group"), "error": r.get("error")})
            continue
        pts = [p for p in series.get(name.lower(), []) if p[0] <= now]
        created = ts(r["created_at"])
        life_days = max(1.0, (now - created).total_seconds() / 86400)
        row = {
            "repo": name, "group": r["group"], "stars": r["stars"], "forks": r["forks"],
            "created": r["created_at"][:7], "release": (r.get("latest_release") or {}).get("tag"),
            "release_at": (r.get("latest_release") or {}).get("published_at"),
            "commits_7d": r.get("commits_7d"), "archived": r.get("archived"),
            "avg_life": r["stars"] / life_days,
        }
        for key, (days, tol) in WINDOWS.items():
            hit = prev7(pts, now - timedelta(days=days), tol)
            if hit and hit[0] < now:
                elapsed = (now - hit[0]).total_seconds() / 86400
                row[f"delta_{key}"] = r["stars"] - hit[1]
                row[f"avg_{key}"] = (r["stars"] - hit[1]) / elapsed
                row[f"base_{key}"] = hit[0].strftime("%Y-%m-%d")
            else:
                row[f"delta_{key}"] = row[f"avg_{key}"] = row[f"base_{key}"] = None
        row["trend"] = (row["avg_30d"] / row["avg_life"]) if row["avg_30d"] is not None else None
        # 이번 주 릴리즈 여부
        row["released_this_week"] = bool(row["release_at"] and ts(row["release_at"]) >= now - timedelta(days=7))
        rows.append(row)

    ok = [r for r in rows if "stars" in r]
    by_week = sorted([r for r in ok if r["delta_7d"] is not None], key=lambda r: -r["delta_7d"])
    by_trend = sorted([r for r in ok if r["trend"] is not None], key=lambda r: -r["trend"])

    report = {
        "as_of": cur["as_of"], "snapshot": cur["_file"],
        "repos": rows,
        "top_weekly_gain": [r["repo"] for r in by_week[:5]],
        "accelerating": [r["repo"] for r in by_trend if r["trend"] >= 1.2],
        "decelerating": [r["repo"] for r in by_trend if r["trend"] < 0.8],
        "released_this_week": [{"repo": r["repo"], "tag": r["release"], "at": r["release_at"]} for r in ok if r["released_this_week"]],
        "candidates_ranked": rank_candidates(snaps, cur, now, json.loads((ROOT / "watchlist.json").read_text())["relevance"])[:20],
        "candidate_pool_size": len(cur.get("candidates") or {}),
        "ecosystem_new_repos_by_month": cur.get("ecosystem_new_repos_by_month", {}),
        "missing_7d": [r["repo"] for r in ok if r["delta_7d"] is None],
        "missing_30d": [r["repo"] for r in ok if r["delta_30d"] is None],
    }

    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{cur['_file']}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")

    order = ["spec", "loop", "skills", "candidate"]
    lines = [f"# SDD 지표 {cur['_file']} (기준 {cur['as_of']})", "",
             "| 구분 | 저장소 | 스타 | 주간 증가 | 일평균(전체) | 일평균(30일) | 추세 | 최신 릴리즈 | 7일 커밋 |",
             "| --- | --- | ---: | ---: | ---: | ---: | --- | --- | ---: |"]
    for g in order:
        for r in sorted([x for x in ok if x["group"] == g], key=lambda x: -x["stars"]):
            wk = f"+{fmt(r['delta_7d'])}" if r["delta_7d"] is not None else "—"
            rel = (r["release"] or "—") + (" (이번 주)" if r["released_this_week"] else "")
            lines.append(f"| {GROUP_KO.get(g, g)} | [{r['repo']}](https://github.com/{r['repo']}) | {fmt(r['stars'])} | {wk} | "
                         f"{fmt(r['avg_life'])} | {fmt(r['avg_30d'])} | {trend_label(r['trend'])} | {rel} | {fmt(r['commits_7d'])} |")
    if report["candidates_ranked"]:
        lines += ["", f"## 관찰 후보(자동 탐지, 풀 {report['candidate_pool_size']}개 중 신호 있는 것)", "",
                  "| 관련성 | 저장소 | 스타 | 주간 증가 | 생성 | 신호 | 설명 |", "| --- | --- | ---: | ---: | --- | --- | --- |"]
        for c in report["candidates_ranked"][:15]:
            wk = f"+{fmt(c['delta_7d'])}" if c["delta_7d"] is not None else "—"
            lines.append(f"| {c['relevance']} | [{c['repo']}](https://github.com/{c['repo']}) | {fmt(c['stars'])} | {wk} | {c['created']} | "
                         f"{', '.join(c['signals'])} | {c['description'][:70]} |")
    (out_dir / f"{cur['_file']}.md").write_text("\n".join(lines) + "\n")
    print(f"wrote reports/{cur['_file']}.json, .md")


if __name__ == "__main__":
    main()
