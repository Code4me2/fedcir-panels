"""Build a test sample from the court's official opinion RSS feed: download each OPINION PDF, extract header fields."""
import csv, json, re, subprocess, sys, time, html, urllib.request, os
sys.path.insert(0, os.path.dirname(__file__))
from extract_header import extract

feed_path, out_dir = sys.argv[1], sys.argv[2]
pdf_dir = os.path.join(out_dir, "pdfs"); os.makedirs(pdf_dir, exist_ok=True)
s = open(feed_path, encoding="utf-8").read()
rows = []
for it in re.findall(r"<item>(.*?)</item>", s, re.S):
    title = html.unescape(re.search(r"<title>(.*?)</title>", it, re.S).group(1))
    if "[OPINION]" not in title:
        continue
    body = html.unescape(re.search(r"<content:encoded>(.*?)</content:encoded>", it, re.S).group(1))
    pdf = re.search(r'href="([^"]+\.pdf)"', body).group(1)
    pdf = pdf if pdf.startswith("http") else "https://www.cafc.uscourts.gov" + pdf
    origin = (re.search(r"Origin:\s*([A-Z]+)", re.sub(r"<[^>]+>", " ", body)) or [None, ""])[1]
    status = "Precedential" if title.rstrip().endswith("Precedential") and "Nonprecedential" not in title else "Nonprecedential"
    appeal, name = re.match(r"([\d-]+):\s*(.*?)\s*\[OPINION\]", title).groups()
    date = (re.search(r"(\d{1,2}-\d{1,2}-\d{4})_\d+\.pdf", pdf) or re.search(r"(\d+-\d+-\d{4})", pdf)).group(1)
    rows.append(dict(appeal_number=appeal, case_name=name, release_date=date, origin=origin, status=status, pdf_url=pdf))

for r in rows:
    fn = os.path.join(pdf_dir, os.path.basename(r["pdf_url"]))
    if not os.path.exists(fn):
        req = urllib.request.Request(r["pdf_url"], headers={"User-Agent": "Mozilla/5.0 (fedcir-panel-research)"})
        open(fn, "wb").write(urllib.request.urlopen(req, timeout=60).read())
        time.sleep(1.5)  # be polite to the court's server
    text = subprocess.run(["pdftotext", "-l", "3", fn, "-"], capture_output=True, text=True).stdout
    e = extract(text)
    r.update(panel="; ".join(e["panel"] or []), author=e["author"] or "", separate_opinions="; ".join(e["separate_opinions"]),
             panel_line=e["panel_raw"] or "", flag="" if (e["panel"] and len(e["panel"]) == 3 and e["author"]) else "CHECK")

cols = ["release_date", "appeal_number", "case_name", "origin", "status", "panel", "author", "separate_opinions", "flag", "panel_line", "pdf_url"]
with open(os.path.join(out_dir, "sample_results.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
print(len(rows), "opinions;", sum(r["flag"] == "CHECK" for r in rows), "flagged")
