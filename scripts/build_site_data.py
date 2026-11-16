"""Build the dashboard's data files (docs/data/) from the archive and the AI classification.

  python3 scripts/build_site_data.py            (full run plus weekly updates: results/full_v1_part*, results/update_*)
  python3 scripts/build_site_data.py --test     (development only: the 50-case test results, v2)

The files are reshaped, not summarized: every statistic on the dashboard is counted in the browser
(docs/app.js) from these tables, so filters (forum, pro se, years) work without a rebuild and each
number can be traced to its cases.

  docs/data/archive.json  one row per decision (text-rule fields) and one row per AI-coded issue
  docs/data/quotes/<code>.json  description and supporting quote per coded issue, loaded on demand
  docs/data/meta.json  counts, side definitions and issue list, for the methodology page

Rules applied here (see CLAUDE.md for the methodology):
- Panel, author, dates, origin, precedential, pro se come from data/decisions.csv (text rules).
- Only written opinions are classified; Rule 36 judgments carry no issues.
- A dissenting judge named by the AI is matched to the panel by surname; names that match no panel
  judge are counted in the build report and ignored.
"""
import argparse, csv, glob, json, re, statistics, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/data"
CLASSIFICATION = "Classification v1: Claude Haiku 5.5, November 2026"
# The full run, then the weekly updates (scripts/update.py), oldest first. If a decision appears in more
# than one file (a failed request retried later), the last successful record is used.
FULL = ("results/full_v1_part*_claude-haiku-5-5.jsonl", "results/update_*_claude-haiku-5-5.jsonl")
TEST = ("results/classification_test_50_claude-haiku-5-5_v2.jsonl", "samples/classification_test_50.csv")

FAVORED = ["side_a", "side_b", "mixed", "other_unclear"]
DISPOSITIONS = ["affirmed", "reversed", "vacated", "vacated and remanded", "reversed and remanded",
                "affirmed in part", "dismissed", "remanded", "other"]


def norm(name):
    """Surname as the text rules write it: upper case, straight apostrophe, no titles."""
    n = name.replace("’", "'").upper().strip()
    n = re.sub(r"\b(CHIEF|SENIOR|CIRCUIT|DISTRICT|JUDGE|J\.)\b", "", n)
    return re.sub(r"\s+", " ", n).strip(" ,.")


def load_results(test):
    if test:
        ids = {r["test_id"]: r["key"] for r in csv.DictReader(open(ROOT / TEST[1]))}
        recs = [json.loads(l) for l in open(ROOT / TEST[0])]
        for r in recs:
            r["key"] = ids[r["id"]]
        return recs, [TEST[0]]
    files = [f for pattern in FULL for f in sorted(glob.glob(str(ROOT / pattern)))]
    latest = {}
    for f in files:
        for line in open(f):
            r = json.loads(line)
            if r.get("coding") or r["key"] not in latest:
                latest[r["key"]] = r
    return list(latest.values()), [str(Path(f).relative_to(ROOT)) for f in files]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="use the 50-case test results (development only)")
    a = ap.parse_args()

    decisions = list(csv.DictReader(open(ROOT / "data/decisions.csv")))
    decisions.sort(key=lambda r: (r["decided_iso"], r["key"]))
    issues = list(csv.DictReader(open(ROOT / "data/issue_list.csv")))
    sides = list(csv.DictReader(open(ROOT / "data/sides.csv")))
    results, files = load_results(a.test)
    if not results:
        raise SystemExit("no classification results found")

    judges, jidx = [], {}

    def judge(name):
        if name not in jidx:
            jidx[name] = len(judges)
            judges.append(name)
        return jidx[name]

    origins = sorted({r["origin"] for r in decisions})
    ctypes = [s["case_type"] for s in sides]
    dec_rows, dindex = [], {}
    for i, r in enumerate(decisions):
        panel = [judge(j.strip()) for j in r["panel"].split(";") if j.strip()]
        au = r["author"]
        author = -1 if au.startswith("PER CURIAM") else (-2 if not au else judge(au))
        argued = r["argued"]
        flags = [f.strip() for f in r["flag"].split(",") if f.strip()]
        dec_rows.append([
            r["decided_iso"], r["case_name"], r["appeal_numbers"], origins.index(r["origin"]),
            1 if r["doc_type"] == "Rule 36" else 0,
            1 if r["precedential"] == "Precedential" else 0,
            1 if r["pro_se"] == "yes" else 0,
            panel, author,
            argued if re.match(r"\d{4}-", argued) else ("?" if argued else ""),
            int(r["days_to_decision"]) if r["days_to_decision"] else None,
            1 if "en banc" in r["flag"] else 0,
            1 if "superseded" in r["flag"] else 0,
            r["pdf_url"],
        ])
        dindex[r["key"]] = i

    rulings, quotes = [], {}
    report = Counter()
    ai_ctype = {}
    for rec in results:
        report["requests"] += 1
        c = rec.get("coding")
        if not c:
            report["failed: " + (rec.get("stop_reason") or rec.get("status"))] += 1
            continue
        if rec["key"] not in dindex:
            report["key not in archive"] += 1
            continue
        d = dindex[rec["key"]]
        ct = ctypes.index(c["case_type"])
        ai_ctype[d] = ct
        panel = dec_rows[d][7]
        surnames = {norm(judges[j].replace(" (visiting)", "")): j for j in panel}
        # cross-check: AI panel vs text-rule panel
        ai_panel = {norm(x) for x in c["panel_judges"]}
        if panel and ai_panel != set(surnames):
            report["cross-check: panel differs"] += 1
        for iss in c["issues"]:
            dis = []
            for name in iss["dissenting_judges"]:
                j = surnames.get(norm(name))
                if j is None:
                    report["dissenter not on panel (ignored)"] += 1
                else:
                    dis.append(j)
            n = len(rulings)
            rulings.append([d, iss["code"], ct, FAVORED.index(iss["favored"]),
                            DISPOSITIONS.index(iss["disposition"]), sorted(set(dis))])
            quotes.setdefault(iss["code"], {})[n] = [iss["description"], iss["quote"]]
            report["issues coded"] += 1
            if iss["code"] == "X99":
                report["X99 issues"] += 1

    # most common AI case type per origin, so the dashboard can guess a calendar case's type
    by_origin = {}
    for d, ct in ai_ctype.items():
        by_origin.setdefault(origins[dec_rows[d][3]], Counter())[ctypes[ct]] += 1
    origin_ctypes = {o: [k for k, _ in cnt.most_common()] for o, cnt in by_origin.items()}

    opinions = [r for r in dec_rows if r[4] == 0]
    meta = {
        "built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "test_data": a.test,
        "classification": CLASSIFICATION + (" (TEST SAMPLE OF 50 CASES - NOT FOR PUBLICATION)" if a.test else ""),
        "latest_decision": dec_rows[-1][0],
        "first_decision": dec_rows[0][0],
        "decisions": len(dec_rows), "opinions": len(opinions), "rule36": len(dec_rows) - len(opinions),
        "classified": len(ai_ctype), "report": dict(report), "result_files": files,
        "court_median_days": statistics.median([r[10] for r in opinions if r[10] is not None]),
    }
    archive = {
        "meta": meta,
        "judges": judges,
        "origins": origins,
        "case_types": [{"name": s["case_type"], "side_a": s["side_a"], "side_b": s["side_b"], "note": s["note"]}
                       for s in sides],
        "issues": [{k: i[k] for k in ("code", "group", "issue", "covers", "side_a_label", "side_b_label")}
                   for i in issues],
        "favored": FAVORED, "dispositions": DISPOSITIONS,
        "origin_case_types": origin_ctypes,
        "decision_fields": ["date", "name", "appeals", "origin", "rule36", "precedential", "pro_se", "panel",
                            "author", "argued", "days", "en_banc", "superseded", "pdf"],
        "decisions": dec_rows,
        "ruling_fields": ["decision", "code", "case_type", "favored", "disposition", "dissenters"],
        "rulings": rulings,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "archive.json").write_text(json.dumps(archive, separators=(",", ":")))
    # small file for methodology.html: counts, side definitions and the issue list (no per-decision rows)
    (OUT / "meta.json").write_text(json.dumps({k: archive[k] for k in ("meta", "case_types", "issues")}, separators=(",", ":")))
    qdir = OUT / "quotes"
    qdir.mkdir(exist_ok=True)
    for old in qdir.glob("*.json"):
        old.unlink()
    for code, q in quotes.items():
        (qdir / f"{code}.json").write_text(json.dumps(q, separators=(",", ":")))
    size = (OUT / "archive.json").stat().st_size / 1e6
    print(f"docs/data/archive.json: {len(dec_rows)} decisions, {len(rulings)} coded issues, {size:.1f} MB")
    for k, v in sorted(report.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
