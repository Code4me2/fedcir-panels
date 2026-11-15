"""Read the court's monthly argument calendars into docs/data/calendar.json.

  python3 scripts/fetch_calendar.py            (downloads the calendars linked from the court's page)
  python3 scripts/fetch_calendar.py FILE.pdf   (parses local PDFs instead, for testing)

Source: /home/oral-argument/scheduled-cases/ links PublicCalendar-<Month><Year>.pdf files. Each lists
sessions ("Panel B: Monday, December 7, 2026, 10:00 A.M., Courtroom 201") and, under each, one line per
case: appeal number, origin code, case name, [argued] or [on the briefs]. Long case names wrap onto a
second line; "Arguing Counsel:" lines (added after a session) are ignored. The court revises these PDFs,
so this runs daily. The calendar has no judges' names: the panel is posted on the daily schedule page
about one hour before argument.
"""
import json, re, subprocess, sys, tempfile, time, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.cafc.uscourts.gov"
PAGE = BASE + "/home/oral-argument/scheduled-cases/"
UA = "fedcir-panel-research; public-records research script"
OUT = ROOT / "docs/data/calendar.json"

SESSION = re.compile(r"^\s*Panel\s+([A-Z]{1,2}):\s*\w+,\s*(\w+ \d{1,2}, \d{4}),\s*([\d:]+\s*[AP]\.M\.),\s*Courtroom\s*(\d+)")
CASE = re.compile(r"^\s*(\d{2}-\d{4})\s+([A-Z]+)\s+(.*?)\s*(\[(argued|on the briefs)\])?\s*$")
REVISED = re.compile(r"\(Revised ([A-Z][a-z]+ \d{1,2}, \d{4})\)")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def parse(text, source):
    sessions, cur, last = [], None, None
    revised = REVISED.search(text)
    for line in text.replace("\f", "\n").splitlines():
        if not line.strip() or "Arguing Counsel" in line:
            last = None if "Arguing Counsel" in line else last
            continue
        m = SESSION.match(line)
        if m:
            cur = {"panel": m.group(1), "date": datetime.strptime(m.group(2), "%B %d, %Y").date().isoformat(),
                   "time": m.group(3).replace(" ", ""), "courtroom": m.group(4), "cases": []}
            sessions.append(cur)
            last = None
            continue
        m = CASE.match(line)
        if m and cur is not None:
            last = {"appeal": m.group(1), "origin": m.group(2), "name": m.group(3),
                    "argued": m.group(5) != "on the briefs" if m.group(5) else None}
            cur["cases"].append(last)
        elif last is not None and cur is not None and line.startswith(" " * 10):
            # wrapped case name, possibly carrying the [argued] marker
            extra = re.sub(r"\s*\[(argued|on the briefs)\]\s*$", "", line).strip()
            last["name"] += " " + extra
            if "[argued]" in line or "[on the briefs]" in line:
                last["argued"] = "[argued]" in line
    for s in sessions:
        for c in s["cases"]:
            if c["argued"] is None:
                c["argued"] = True  # marker missing (not seen so far); assume argued
    return {"source": source, "revised": revised.group(1) if revised else "", "sessions": sessions}


def pdf_text(data):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(data)
        f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, check=True).stdout


def main():
    months = []
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            months.append(parse(pdf_text(Path(p).read_bytes()), Path(p).name))
    else:
        page = get(PAGE).decode("utf-8", "replace")
        links = sorted(set(re.findall(r'href="([^"]*PublicCalendar-[A-Za-z]+\d{4}\.pdf)"', page)))
        if not links:
            sys.exit("no calendar links found on " + PAGE)
        for href in links:
            time.sleep(1.5)
            url = href if href.startswith("http") else BASE + href
            months.append(parse(pdf_text(get(url)), url))
    sessions = sorted((s for m in months for s in m["sessions"]), key=lambda s: (s["date"], s["time"], s["panel"]))
    out = {"read": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
           "calendars": [{"source": m["source"], "revised": m["revised"], "sessions": len(m["sessions"])} for m in months],
           "sessions": sessions}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    n = sum(len(s["cases"]) for s in sessions)
    print(f"{len(sessions)} sessions, {n} cases -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
