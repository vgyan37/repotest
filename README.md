# RepoScope — GitHub Repository Quality Analyzer

Uni-Projekt · Valentina Gyan · 3-Säulen-Scoring · Median-Benchmark

## Dateien

```
reposcope/
├── index.html                    ← Analyzer (lädt data/benchmarks.json)
├── analysis.html                 ← Top-100 Tabelle (lädt data/top100_repos.json)
├── collect_data.py               ← Datensammlung
├── requirements.txt              ← Python: requests
├── .github/workflows/collect.yml ← Täglich 06:00 UTC automatisch
└── data/
    ├── benchmarks.json           ← Median je KPI (generiert)
    └── top100_repos.json         ← Top-100 Repos mit Scores (generiert)
```

## Setup

### 1. GitHub Pages aktivieren
Settings → Pages → Branch: `main` → Save

### 2. GitHub Action starten
Actions → "Benchmark-Daten täglich aktualisieren" → Run workflow

Nach ~15 Minuten: `data/` Ordner wird automatisch befüllt.

### 3. Seiten öffnen
```
https://vgyan37.github.io/reposcope/index.html
https://vgyan37.github.io/reposcope/analysis.html
```

## Scoring-Methodik (3 Säulen)

**Formel:** `Score = min(100, Wert / Median × 100)`

| Säule | Gewicht | Kennzahlen |
|-------|--------:|------------|
| ⚡ Aktivität & Community | 40% | Commits/30T (50%) · Tage inaktiv (30%) · Contributors (20%) |
| 🔧 Reaktionsfähigkeit & Wartung | 35% | Close-Rate (25%) · Release-Freq (25%) · Close-Zeit (25%) · Engagement (15%) · Fehlerbehebung (10%) |
| 📡 Reichweite & Dokumentation | 25% | Fork-Ratio (35%) · Doku (35%) · Stars/Alter log (30%) |

**Benchmark:** Median der Top-100 GitHub-Repos nach Stars · täglich aktualisiert

## Rate-Limits

| Situation | Limit |
|-----------|-------|
| Ohne Token (index.html) | 60 Req/h |
| Mit Token (index.html)  | 5.000 Req/h |
| GitHub Action (collect_data.py) | Automatisch via secrets.GITHUB_TOKEN |

---
*Valentina Gyan · Uni-Projekt Softwaretechnik · GitHub REST API v3*
