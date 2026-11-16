"""Weekly update: add new decisions, classify the new opinions, rebuild the dashboard data.

  python3 scripts/update.py                 (what the weekly GitHub Actions job runs)
  python3 scripts/update.py --no-fetch      (skip the court's sitemap; reuse data/sitemap/all_post_urls.txt)
  python3 scripts/update.py --dry-run       (show what would be classified; send nothing to the AI)

Steps, each the same code that built the archive, so new decisions follow exactly the same rules:
1. Re-read the court's sitemap (31 small files, 1 s apart) into data/sitemap/all_post_urls.txt.
   The sitemap is used rather than the RSS feed because it is complete (the feed holds only ~3 weeks,
   so a missed week would leave a gap) and it also lists the argument recordings that give argument dates.
2. scripts/build_archive.py: download only the PDFs not yet in data/text, apply the text rules to all.
3. Collect any earlier update batch that had not finished; then send every written opinion that has no
   AI coding yet (not superseded) as one batch (scripts/classify.py, same instructions and model as v1),
   wait for it, and save results/update_<date>_claude-haiku-5-5.jsonl.
   Safety stop: if more than --max-new opinions need coding, nothing is sent (a bug, not a normal week).
4. scripts/build_site_data.py: rebuild docs/data/.
The GitHub Actions job then commits and pushes; GitHub Pages republishes the site.
"""
import argparse, csv, datetime, glob, json, os, subprocess, sys, types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
MODEL = "claude-haiku-5-5"  # classification v1; changing it means a new classification version (see CLAUDE.md)
RESULT_GLOBS = (f"results/full_v1_part*_{MODEL}.jsonl", f"results/update_*_{MODEL}.jsonl")


def run(*cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)


def fetch_sitemap():
    """Like scripts/fetch_sitemap.py, but keeps only the URL list (the XML files go to work/)."""
    work = ROOT / "work/sitemap"
    run("scripts/fetch_sitemap.py", str(work))
    new = (work / "all_post_urls.txt").read_text().split()
    old = (ROOT / "data/sitemap/all_post_urls.txt").read_text().split()
    if len(new) < 0.95 * len(old):  # a partial download would silently drop decisions
        sys.exit(f"sitemap has {len(new)} URLs, fewer than the {len(old)} saved; not used")
    (ROOT / "data/sitemap/all_post_urls.txt").write_text("\n".join(new))
    print(f"sitemap: {len(new)} posting URLs ({len(set(new) - set(old))} new)")


def coded_keys():
    done, failed = set(), set()
    for pattern in RESULT_GLOBS:
        for f in glob.glob(str(ROOT / pattern)):
            for line in open(f):
                r = json.loads(line)
                (done if r.get("coding") else failed).add(r["key"])
    return done, failed - done


def pending_batches():
    """Update batches submitted earlier whose results were never saved (e.g. the job timed out)."""
    out = []
    for bf in sorted((ROOT / "results/batches").glob(f"batch_update_*_{MODEL}.json")):
        info = json.loads(bf.read_text())
        if not (ROOT / "results" / f"{Path(info['sample']).stem}_{MODEL}.jsonl").exists():
            out.append(info)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wait", type=int, default=150, help="minutes to wait for the batch (default 150)")
    ap.add_argument("--max-new", type=int, default=300)
    a = ap.parse_args()

    if not a.no_fetch:
        fetch_sitemap()
    run("scripts/build_archive.py", "--no-push")

    import classify
    have_key = any(os.environ.get(v) for v in classify.KEY_VARS)
    problems = []
    if not have_key:
        problems.append("no API key (FEDCIR_API_KEY): new opinions were added but not classified")
    elif not a.dry_run:
        for info in pending_batches():
            print(f"collecting earlier batch {info['batch_id']}")
            classify.cmd_collect(types.SimpleNamespace(model=MODEL, sample=info["sample"], tag="", wait=a.wait))

    done, failed = coded_keys()
    in_flight = {r["key"] for info in pending_batches() for r in csv.DictReader(open(ROOT / info["sample"]))}
    todo = [r for r in csv.DictReader(open(ROOT / "data/decisions.csv"))
            if r["doc_type"] == "Opinion" and "superseded" not in r["flag"] and "error" not in r["flag"]
            and r["key"] not in done and r["key"] not in in_flight]
    todo.sort(key=lambda r: (r["decided_iso"], r["key"]))
    print(f"{len(todo)} opinions to classify ({len(failed & {r['key'] for r in todo})} retried after a failed request); "
          f"{len(in_flight)} still in an unfinished batch")
    for r in todo[:20]:
        print(f"  {r['decided_iso']}  {r['appeal_numbers']}  {r['case_name'][:70]}")

    if todo and have_key and not a.dry_run:
        if len(todo) > a.max_new:
            sys.exit(f"STOP: {len(todo)} opinions need coding, more than --max-new {a.max_new}. "
                     "This is not a normal week; check before re-running with a higher --max-new.")
        stamp = datetime.datetime.utcnow().strftime("%Y%m%d")
        sample = ROOT / f"samples/update_{stamp}.csv"
        n = 1
        while sample.exists() or (ROOT / "results/batches" / f"batch_{sample.stem}_{MODEL}.json").exists():
            n += 1
            sample = ROOT / f"samples/update_{stamp}_{n}.csv"
        with open(sample, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "key", "case_name", "appeal_numbers", "decided_iso", "origin"],
                               extrasaction="ignore")
            w.writeheader()
            w.writerows({**r, "id": f"{sample.stem[7:]}-{i:04d}"} for i, r in enumerate(todo, 1))
        rel = str(sample.relative_to(ROOT))
        ns = types.SimpleNamespace(model=MODEL, sample=rel, tag="", wait=a.wait)
        classify.cmd_submit(ns)
        res = classify.cmd_collect(ns)
        if res is None:
            problems.append("batch not finished in time; the next run collects it")
        elif res["problems"]:
            problems.append(f"{len(res['problems'])} requests failed; they are retried next run")

    run("scripts/build_site_data.py")
    for p in problems:
        print("PROBLEM:", p)
    if problems and not a.dry_run:
        sys.exit(1)  # the job is marked failed (GitHub emails the owner) after the data that did work is saved


if __name__ == "__main__":
    main()
