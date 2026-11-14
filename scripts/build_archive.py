"""Build the decision archive (2015 onward) from the court's sitemap.

For each opinion and Rule 36 judgment: download the PDF, extract its text, and pull out
panel, author, separate opinions, decision date, origin and precedential status with text rules.
Match each decision to its argument recording (if any) to get the argument date.

Resumable: documents already downloaded are skipped. Saves progress to GitHub every N documents.

Usage: python3 scripts/build_archive.py [--limit N] [--checkpoint 500] [--no-push]
"""
import argparse, collections, csv, datetime, gzip, json, os, re, subprocess, sys, time, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from extract_header import extract, extract_more

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(REPO, "work")                    # local cache, not saved to GitHub
PDF_DIR, TXT_DIR = os.path.join(WORK, "pdfs"), os.path.join(WORK, "text")
SITE = "https://www.cafc.uscourts.gov"
UA = {"User-Agent": "Mozilla/5.0 (fedcir-panel-research; public-records research script)"}
START = datetime.date(2015, 1, 1)
BACKFILL_DAY = datetime.date(2025, 3, 10)            # bulk re-posting of old decisions
PAUSE = 1.5                                          # seconds between requests to the court
DATE_TAIL = r"-(\d{1,2})-(\d{1,2})-(\d{2,4})(?:_(\d+)|-(\d+))?$"

def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(os.path.join(WORK, "progress.log"), "a") as f: f.write(line + "\n")

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()

def parse_posting(url):
    """Classify a sitemap posting URL. Returns dict or None."""
    slug = url.rstrip("/").rsplit("/", 1)[1].lower()
    m = re.match(r"(\d{1,2})-(\d{1,2})-(\d{4})-", slug)
    if not m: return None
    posted = datetime.date(int(m[3]), int(m[1]), int(m[2]))
    rest = slug[m.end():]
    if slug.endswith("audio-uploaded"):
        n = re.match(r"(\d{4})-(\d{4})", rest)
        return {"kind": "audio", "posted": posted, "appeal": f"{n[1][-2:]}-{n[2]}" if n else None}
    if "errata" in rest: return None
    if "rule_36_judgment" in rest or "rule-36-judgment" in rest: kind = "rule36"
    elif "opinion" in rest and "motion_panel" not in rest: kind = "opinion"
    else: return None
    return {"kind": kind, "posted": posted, "slug": slug, "url": url, "rest": rest}

def appeal_numbers(rest):
    core = re.sub(DATE_TAIL, "", rest)
    nums = set()
    lead = re.match(r"(\d{4}|\d{2})-(\d{4})", core)
    if lead: nums.add(f"{lead[1][-2:]}-{lead[2]}")
    tail = re.split(r"opinion|rule_36_judgment", core)[-1]
    for m in re.finditer(r"(?<!\d)(\d{2}|\d{4})-(\d{4})((?:-\d{4})*)(?!\d)", tail):
        nums.add(f"{m[1][-2:]}-{m[2]}"); nums.update(f"{m[1][-2:]}-{x}" for x in re.findall(r"\d{4}", m[3]))
    return sorted(nums)

def candidate_pdf_urls(rest):
    """Predict the PDF address from the posting slug (avoids fetching the posting page)."""
    m = re.search(r"(\d{2,4}-\d{4})(?:-\d{4})*-(opinion|rule_36_judgment)" + DATE_TAIL, rest)
    if not m: return []
    appeal, dtype, mo, dy, yr, pid, seq = m.groups()
    date = f"{int(mo)}-{int(dy)}-{yr}"
    if pid:  # 2020-21 files use lowercase, later ones uppercase; try both before the posting page
        return [f"{SITE}/opinions-orders/{appeal}.{t}.{date}_{pid}.pdf" for t in (dtype, dtype.upper())]
    if seq: return [f"{SITE}/opinions-orders/{appeal}.{dtype}.{date}.{seq}.pdf"]
    return [f"{SITE}/opinions-orders/{appeal}.{dtype}.{date}.pdf"]

def pdf_from_posting_page(url):
    page = get(url).decode("utf-8", "replace"); time.sleep(PAUSE)
    links = [l for l in re.findall(r'href="([^"]+\.pdf)"', page) if "opinions-orders" in l]
    return (links[0] if links[0].startswith("http") else SITE + links[0]) if links else None

def fetch_pdf(post):
    for u in candidate_pdf_urls(post["rest"]):
        try:
            data = get(u); time.sleep(PAUSE)
            if data[:4] == b"%PDF": return u, data
        except urllib.error.HTTPError:
            time.sleep(PAUSE)
    u = pdf_from_posting_page(post["url"])
    if not u: raise RuntimeError("no PDF link on posting page")
    data = get(u); time.sleep(PAUSE)
    return u, data

def key_for(post):
    return re.sub(r"[^a-z0-9]+", "_", post["slug"])[:180]

def parse_date(s):
    try: return datetime.datetime.strptime(s.replace(".", "").replace(",", ""), "%B %d %Y").date()
    except (ValueError, AttributeError): return None

def save(records, push, n_done):
    """Write decisions.csv and packed text files into the repository, then commit and push."""
    data_dir = os.path.join(REPO, "data"); os.makedirs(os.path.join(data_dir, "text"), exist_ok=True)
    cols = ["key", "decided", "doc_type", "appeal_numbers", "case_name", "origin", "precedential", "panel", "author",
            "separate_opinions", "argued", "days_to_decision", "flag", "panel_line", "pdf_url", "posted", "posting_url"]
    rows = sorted(records.values(), key=lambda r: (r.get("decided_iso") or "", r["key"]))
    with open(os.path.join(data_dir, "decisions.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    by_year = collections.defaultdict(list)
    for r in rows:
        p = os.path.join(TXT_DIR, r["key"] + ".txt")
        if os.path.exists(p): by_year[(r.get("decided_iso") or "unknown")[:4]].append({"key": r["key"], "text": open(p).read()})
    for y, docs in by_year.items():
        with gzip.open(os.path.join(data_dir, "text", f"text_{y}.jsonl.gz"), "wt") as f:
            for d in docs: f.write(json.dumps(d) + "\n")
    if push:
        msg = f"Archive progress: {n_done} decisions processed\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01B3QP8fPLAjgJii7MVSoNS4"
        g = ["git", "-C", REPO, "-c", "user.name=zljacobs24", "-c", "user.email=zljacobs24@users.noreply.github.com"]
        subprocess.run(g + ["add", "data"], check=True)
        if subprocess.run(g + ["diff", "--cached", "--quiet"]).returncode != 0:
            subprocess.run(g + ["commit", "-q", "-m", msg], check=True)
            for attempt in range(4):
                if subprocess.run(g + ["-c", "push.negotiate=true", "push", "-q", "origin", "main"]).returncode == 0: break
                time.sleep(2 ** (attempt + 1))
        log(f"checkpoint saved ({n_done} done)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--checkpoint", type=int, default=500)
    ap.add_argument("--no-push", action="store_true"); ap.add_argument("--extract-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(PDF_DIR, exist_ok=True); os.makedirs(TXT_DIR, exist_ok=True)

    posts = [p for p in map(parse_posting, open(os.path.join(REPO, "data/sitemap/all_post_urls.txt")).read().split()) if p]
    # Argument dates: skip bulk-upload days (posting date is not the argument date there)
    per_day = collections.Counter(p["posted"] for p in posts if p["kind"] == "audio")
    bulk_days = {d for d, n in per_day.items() if n > 100}
    argued_any, argued_date = collections.defaultdict(bool), collections.defaultdict(list)
    for p in posts:
        if p["kind"] == "audio" and p["appeal"]:
            argued_any[p["appeal"]] = True
            if p["posted"] not in bulk_days: argued_date[p["appeal"]].append(p["posted"])
    log(f"bulk recording-upload days excluded from argument dates: {sorted(map(str, bulk_days))}")

    decisions = [p for p in posts if p["kind"] in ("opinion", "rule36") and p["posted"] >= START and p["posted"] != BACKFILL_DAY]
    if a.limit: decisions = decisions[:: max(1, len(decisions) // a.limit)][: a.limit]
    log(f"{len(decisions)} decision postings to process")

    records, done = {}, 0
    for p in decisions:
        k = key_for(p); txt_path = os.path.join(TXT_DIR, k + ".txt"); meta_path = os.path.join(TXT_DIR, k + ".url")
        r = {"key": k, "doc_type": "Rule 36" if p["kind"] == "rule36" else "Opinion", "posted": str(p["posted"]),
             "posting_url": p["url"], "appeal_numbers": "; ".join(appeal_numbers(p["rest"]))}
        try:
            if not os.path.exists(txt_path):
                if a.extract_only: continue
                pdf_url, data = fetch_pdf(p)
                pdf_path = os.path.join(PDF_DIR, os.path.basename(pdf_url)); open(pdf_path, "wb").write(data)
                text = subprocess.run(["pdftotext", pdf_path, "-"], capture_output=True, text=True).stdout
                open(txt_path, "w").write(text); open(meta_path, "w").write(pdf_url)
            text, r["pdf_url"] = open(txt_path).read(), open(meta_path).read()
            e, x = extract(text), extract_more(text)
            r.update(decided=x["decided"], precedential="Nonprecedential" if p["kind"] == "rule36" else x["precedential"],
                     origin=x["origin_from_text"], panel="; ".join(e["panel"] or []), author=e["author"] or "",
                     separate_opinions="; ".join(e["separate_opinions"]), panel_line=e["panel_raw"] or "")
            name = re.sub(r"^(\d{2,4}-[\dm]{4}-)", "", p["rest"])
            r["case_name"] = re.split(r"-(?:opinion|rule-36-judgment|rule_36_judgment)", name)[0].replace("-", " ").strip()
        except Exception as ex:
            r["flag"] = f"download/extract error: {ex!r}"[:200]; records[k] = r; done += 1; log(f"ERROR {k}: {ex!r}"); continue

        decided = parse_date(r["decided"]); r["decided_iso"] = str(decided) if decided else ""
        nums = r["appeal_numbers"].split("; ") if r["appeal_numbers"] else []
        dates = sorted(d for n in nums for d in argued_date.get(n, []) if decided and d <= decided)
        r["argued"] = str(dates[-1]) if dates else ("yes (date unknown)" if any(argued_any.get(n) for n in nums) else "")
        r["days_to_decision"] = (decided - dates[-1]).days if dates else ""
        panel = r["panel"].split("; ") if r["panel"] else []
        probs = []
        if len(panel) != 3: probs.append("panel")
        if not r["author"]: probs.append("author")
        elif not r["author"].startswith("PER CURIAM") and r["author"] not in panel: probs.append("author not on panel")
        for s in r["separate_opinions"].split("; "):
            if s and s.split(": ")[-1] not in panel: probs.append("separate-opinion judge not on panel")
        if not decided: probs.append("date")
        elif decided < START: probs.append("decided before 2015")
        if not r["origin"]: probs.append("origin")
        if not nums: probs.append("appeal number")
        r["flag"] = ", ".join(probs)
        records[k] = r; done += 1
        if done % 100 == 0: log(f"{done}/{len(decisions)} processed")
        if done % a.checkpoint == 0: save(records, not a.no_push, done)
    save(records, not a.no_push, done)
    flags = collections.Counter(f for r in records.values() for f in (r.get("flag") or "").split(", ") if f)
    log(f"DONE: {done} decisions; flags: {dict(flags)}")

if __name__ == "__main__":
    main()
