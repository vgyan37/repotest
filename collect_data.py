#!/usr/bin/env python3
"""
RepoScope — Datensammlung & Benchmark-Berechnung
Valentina Gyan · Uni-Projekt

Schreibt:
  data/benchmarks.json    — Median je KPI (→ wird von index.html geladen)
  data/top100_repos.json  — Top-N Repos mit Scores (→ wird von analysis.html geladen)

Verwendung:
  pip install requests
  export GITHUB_TOKEN=ghp_xxx
  python collect_data.py [--n 100]
"""

import json, os, sys, time, math, statistics, argparse
from datetime import datetime, timezone
import requests

TOKEN   = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"
API     = "https://api.github.com"


# ── API ──────────────────────────────────────────────────────────
def get(url, params=None, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        except requests.RequestException as e:
            print(f"  Netzwerkfehler: {e}"); time.sleep(2); continue
        if r.status_code == 200: return r.json()
        if r.status_code == 202: time.sleep(3); continue
        if r.status_code in (403, 429):
            wait = min(int(r.headers.get("X-RateLimit-Reset", time.time()+10)) - int(time.time()) + 2, 60)
            print(f"  Rate Limit — warte {wait}s"); time.sleep(wait); continue
        if r.status_code == 404: return None
        return None
    return None


# ── Top-N Repos holen ─────────────────────────────────────────────
def fetch_top_repos(n):
    repos, page = [], 1
    while len(repos) < n:
        per = min(50, n - len(repos))
        r = requests.get(f"{API}/search/repositories",
            headers=HEADERS, timeout=20,
            params={"q":"stars:>5000 is:public archived:false",
                    "sort":"stars","order":"desc","per_page":per,"page":page})
        if r.status_code != 200: break
        data = r.json().get("items", [])
        repos.extend(data)
        page += 1
        if len(data) < per: break
        time.sleep(1.5)
    return repos[:n]


# ── KPIs für ein Repo berechnen ───────────────────────────────────
def calc_kpis(base, owner, name):
    b = f"{API}/repos/{owner}/{name}"

    activity     = get(f"{b}/stats/commit_activity")
    readme       = get(f"{b}/readme")
    contributing = get(f"{b}/contents/CONTRIBUTING.md")
    releases_raw = get(f"{b}/releases",   {"per_page": 20})
    issues_raw   = get(f"{b}/issues",     {"state": "all", "per_page": 100})
    contribs_raw = get(f"{b}/contributors",{"per_page": 100})

    # Commits letzte 30 Tage
    commits30 = None
    if isinstance(activity, list) and len(activity) >= 4:
        commits30 = sum(w.get("total", 0) for w in activity[-4:])

    # Tage seit letztem Commit
    pushed       = base.get("pushed_at", "")
    days_inactive = max(0, int((time.time() - datetime.fromisoformat(
        pushed.replace("Z","+00:00")).timestamp()) / 86400)) if pushed else None

    # Contributors
    contrib_count = len([c for c in (contribs_raw or []) if c.get("type") == "User"]) or None

    # Issues
    close_rate = avg_close = avg_comments = fehler_prod = None
    if isinstance(issues_raw, list) and issues_raw:
        real = [i for i in issues_raw if "pull_request" not in i]
        if real:
            closed     = [i for i in real if i["state"] == "closed"]
            close_rate = len(closed) / len(real)
            times      = [(datetime.fromisoformat(i["closed_at"].replace("Z","+00:00")) -
                           datetime.fromisoformat(i["created_at"].replace("Z","+00:00"))).days
                          for i in closed if i.get("closed_at") and i.get("created_at")]
            times      = [t for t in times if t >= 0]
            avg_close  = statistics.mean(times) if times else None
            avg_comments = statistics.mean([i.get("comments", 0) for i in real])
            if commits30 and commits30 > 0:
                fehler_prod = len(closed) / commits30

    # Release-Frequenz
    rel_freq = None
    if isinstance(releases_raw, list):
        stable = sorted([r for r in releases_raw
                         if not r.get("draft") and not r.get("prerelease") and r.get("published_at")],
                        key=lambda r: r["published_at"])
        if len(stable) >= 2:
            diffs = [(datetime.fromisoformat(stable[i+1]["published_at"].replace("Z","+00:00")) -
                      datetime.fromisoformat(stable[i]["published_at"].replace("Z","+00:00"))).days
                     for i in range(len(stable)-1)]
            rel_freq = statistics.mean(diffs) if diffs else None

    # Säule 3
    stars       = base.get("stargazers_count", 0)
    forks       = base.get("forks_count", 0)
    age         = max(1, int((time.time() - datetime.fromisoformat(
        base["created_at"].replace("Z","+00:00")).timestamp()) / 86400))
    fork_ratio  = forks / stars if stars > 0 else 0
    stars_tage  = stars / age
    readme_ok   = bool(readme)
    contrib_ok  = bool(contributing)
    doku        = (60 if readme_ok else 0) + (40 if contrib_ok else 0)

    return {
        "commits30":    commits30,
        "daysInactive": days_inactive,
        "contributors": contrib_count,
        "closeRate":    round(close_rate, 4)    if close_rate   is not None else None,
        "relFreq":      round(rel_freq, 2)      if rel_freq     is not None else None,
        "avgClose":     round(avg_close, 2)     if avg_close    is not None else None,
        "avgComments":  round(avg_comments, 2)  if avg_comments is not None else None,
        "fehlerProd":   round(fehler_prod, 4)   if fehler_prod  is not None else None,
        "forkRatio":    round(fork_ratio, 4),
        "doku":         doku,
        "starsTage":    round(stars_tage, 3),
        "readmePresent":  readme_ok,
        "contribPresent": contrib_ok,
    }


# ── Median berechnen ─────────────────────────────────────────────
def safe_median(values):
    vals = sorted([v for v in values if v is not None and math.isfinite(v)])
    if not vals: return None
    n, m = len(vals), len(vals) // 2
    return round(vals[m] if n % 2 else (vals[m-1] + vals[m]) / 2, 4)


# ── Scoring ───────────────────────────────────────────────────────
KPI_DIR = {
    "commits30":    "more", "daysInactive": "less",  "contributors": "more",
    "closeRate":    "more", "relFreq":      "less",  "avgClose":     "less",
    "avgComments":  "more", "fehlerProd":   "more",
    "forkRatio":    "more", "doku":         "bool",  "starsTage":    "log",
}
KPI_WEIGHTS = {
    "p1": {"commits30": .50, "daysInactive": .30, "contributors": .20},
    "p2": {"closeRate": .25, "relFreq": .25, "avgClose": .25,
           "avgComments": .15, "fehlerProd": .10},
    "p3": {"forkRatio": .35, "doku": .35, "starsTage": .30},
}

def score_kpi(key, val, med):
    if val is None or med is None: return None
    d = KPI_DIR.get(key)
    if d == "more":  return min(100, round(val / med * 100)) if med > 0 else None
    if d == "less":  return 100 if val == 0 else (min(100, round(med / val * 100)) if med > 0 else None)
    if d == "bool":  return val
    if d == "log":
        if val <= 0 or med <= 0: return None
        lv, lm = math.log10(val), math.log10(med)
        return min(100, round(lv / lm * 100)) if lm > 0 else None

def score_repo(kpis, medians):
    def pillar(pid):
        w = KPI_WEIGHTS[pid]; pts = wt = 0
        for key, weight in w.items():
            s = score_kpi(key, kpis.get(key), medians.get(key))
            if s is not None: pts += s * weight; wt += weight
        return round(pts / wt) if wt > 0 else None
    p1, p2, p3 = pillar("p1"), pillar("p2"), pillar("p3")
    parts = [(s, w) for s, w in [(p1,.4),(p2,.35),(p3,.25)] if s is not None]
    total = round(sum(s*w for s,w in parts) / sum(w for _,w in parts)) if parts else None
    return {"p1": p1, "p2": p2, "p3": p3, "overall": total}


# ── Main ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    args = parser.parse_args()
    os.makedirs("data", exist_ok=True)

    print(f"=== RepoScope · Datensammlung ===")
    print(f"Token: {'✓' if TOKEN else '✗ (langsam ohne Token)'}")
    print(f"Ziel: Top-{args.n} Repos\n")

    # 1. Repos holen
    print(f"[1/4] Top-{args.n} Repos laden…")
    repos = fetch_top_repos(args.n)
    print(f"  → {len(repos)} Repos\n")

    # 2. KPIs berechnen
    print(f"[2/4] KPIs berechnen…")
    all_data = []
    for i, repo in enumerate(repos):
        owner, name = repo["owner"]["login"], repo["name"]
        print(f"  [{i+1:3d}/{len(repos)}] {owner}/{name}")
        try:
            kpis = calc_kpis(repo, owner, name)
            stars  = repo["stargazers_count"]
            forks  = repo["forks_count"]
            age    = max(1, int((time.time() - datetime.fromisoformat(
                repo["created_at"].replace("Z","+00:00")).timestamp()) / 86400))
            all_data.append({
                "rank":        i + 1,
                "full_name":   repo["full_name"],
                "html_url":    repo["html_url"],
                "description": repo.get("description", ""),
                "language":    repo.get("language"),
                "license":     (repo.get("license") or {}).get("spdx_id"),
                "stars": stars, "forks": forks,
                "open_issues": repo.get("open_issues_count", 0),
                "age_days": age, "created_at": repo["created_at"],
                "kpis": kpis,
            })
        except Exception as e:
            print(f"    FEHLER: {e}")
        time.sleep(0.15)

    # 3. Median berechnen
    print(f"\n[3/4] Median berechnen…")
    KPI_KEYS = ["commits30","daysInactive","contributors","closeRate",
                "relFreq","avgClose","avgComments","fehlerProd","forkRatio","starsTage"]
    medians = {k: safe_median([d["kpis"].get(k) for d in all_data]) for k in KPI_KEYS}
    medians["daysInactive"] = max(medians.get("daysInactive") or 1, 1)
    for k, v in medians.items():
        print(f"  {k:<20}: {v:.4f}" if v else f"  {k:<20}: N/A")

    # 4. Scoren & schreiben
    print(f"\n[4/4] Scoren & Dateien schreiben…")
    for repo in all_data:
        repo["scores"] = score_repo(repo["kpis"], medians)

    all_data.sort(key=lambda x: (x["scores"].get("overall") or 0), reverse=True)
    for i, r in enumerate(all_data): r["rank"] = i + 1

    now = datetime.now(timezone.utc).isoformat()

    # benchmarks.json
    lang_freq = {}
    for d in all_data:
        l = d.get("language")
        if l: lang_freq[l] = lang_freq.get(l, 0) + 1

    bm = {
        "generated_at": now,
        "sample_size":  len(all_data),
        "medians":      medians,
        "top_languages": sorted(lang_freq.items(), key=lambda x: -x[1])[:10],
    }
    with open("data/benchmarks.json", "w") as f:
        json.dump(bm, f, indent=2, default=str)
    print("  ✓ data/benchmarks.json")

    # top100_repos.json
    with open("data/top100_repos.json", "w") as f:
        json.dump(all_data, f, indent=2, default=str)
    print(f"  ✓ data/top100_repos.json")

    scores = [d["scores"].get("overall") for d in all_data if d["scores"].get("overall")]
    avg    = round(sum(scores)/len(scores)) if scores else 0
    print(f"\n✅ Fertig! {len(all_data)} Repos · Ø Score: {avg}")

if __name__ == "__main__":
    main()
