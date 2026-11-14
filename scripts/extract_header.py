"""Extract panel, author, and separate opinions from Federal Circuit opinion text (free text rules, no AI)."""
import re

TITLE = r"(?:Chief|Circuit|Senior Circuit|District|Senior District|Chief District|Senior|Judge)"
NAME = r"[A-Z][A-Z'\-]+(?: [A-Z][A-Z'\-]+)?"

def norm(t):
    t = t.replace("’", "'").replace(" ", " ")
    return re.sub(r"[ \t]+", " ", t)

def parse_panel(text):
    """Return list of judge surnames from the 'Before ...' line, or a Rule 36 'PER CURIAM (...)' line."""
    r36 = re.search(r"PER CURIAM\s*\(([^)]{5,200})\)", text)
    if r36 and re.search(r"Fed\.\s*Cir\.\s*R\.\s*36", text):
        raw = re.sub(r"\s+", " ", r36.group(1))
        cleaned = re.sub(r",?\s*(?:Chief|Circuit|Senior Circuit|Senior|District|Chief District|Senior District)?\s*Judges?\.?\*?", ",", raw)
        names = [n.strip(" .*,") for n in re.split(r",|\band\b", cleaned)]
        return [n for n in names if re.fullmatch(NAME, n)], raw
    m = re.search(r"\bBefore\s+(.{5,300}?(?:Judges?|Justice)\.?)[\s\*\d†‡]*\n", text, re.S)
    if not m:
        return None, None
    raw = re.sub(r"\s+", " ", m.group(1))
    # Drop titles like "Chief Judge", "Circuit Judges", "District Judge"
    cleaned = re.sub(r",?\s*(?:Chief|Circuit|Senior Circuit|Senior|District|Chief District|Senior District)?\s*Judges?\.?\*?", ",", raw)
    names = [n.strip(" .*,") for n in re.split(r",|\band\b", cleaned)]
    names = [n for n in names if re.fullmatch(NAME, n)]
    return names, raw

def parse_author(text, panel_end):
    after = text[panel_end:panel_end + 3000]
    if re.search(r"Opinion for the court filed\s+PER CURIAM|^\s*PER CURIAM\.?\s*$", after, re.M | re.I):
        return "PER CURIAM"
    m = re.search(rf"Opinion for the court filed by\s+(?:{TITLE}\s+)*Judges?\s+({NAME})", re.sub(r"\s+", " ", after))
    if m:
        return m.group(1)
    m = re.search(rf"^\s*({NAME}),\s*(?:Chief|Circuit|Senior Circuit|District|Chief District|Senior District)\s+Judge\.?\s*$", after, re.M)
    return m.group(1) if m else None

def parse_separate(text):
    flat = re.sub(r"\s+", " ", text[:8000])
    out = []
    for m in re.finditer(rf"((?:Opinion )?(?:[Cc]oncurring|[Dd]issenting|[Cc]oncurring in part and dissenting in part|[Dd]issenting in part)[a-z ]*?) (?:opinion )?filed by (?:{TITLE} )*Judges? ({NAME})", flat):
        kind = "dissent" if "issent" in m.group(1) else "concurrence"
        if "oncurring in part and dissenting" in m.group(1): kind = "partial dissent"
        out.append(f"{kind}: {m.group(2)}")
    return sorted(set(out))

def extract(text):
    text = norm(text)
    if re.search(r"AFFIRMED\.\s*See Fed\.\s*Cir\.\s*R\.\s*36", text):
        panel, raw = parse_panel(text)
        return {"panel": panel, "panel_raw": raw, "author": "PER CURIAM (RULE 36)", "separate_opinions": []}
    m = re.search(r"\bBefore\s+", text)
    panel, raw = parse_panel(text)
    end = text.find(raw.split()[-1]) + 1 if raw else (m.end() if m else 0)
    return {
        "panel": panel,
        "panel_raw": raw,
        "author": parse_author(text, end) if raw else None,
        "separate_opinions": parse_separate(text),
    }


ORIGINS = [
    ("PTO", r"Patent and Trademark Office|Patent Trial and Appeal Board|Board of Patent Appeals"),
    ("ITC", r"International Trade Commission"),
    ("DCT", r"United States District Court"),
    ("CFC", r"Court of Federal Claims"),
    ("CAVC", r"Court of Appeals for Veterans Claims"),
    ("MSPB", r"Merit Systems Protection Board"),
    ("CIT", r"Court of International Trade"),
    ("BCA", r"Board of Contract Appeals"),
    ("TTAB", r"Trademark Trial and Appeal Board"),
    ("ARB", r"arbitrator"),
]

def extract_more(text):
    text = norm(text)
    head = re.sub(r"\s+", " ", text[:6000])
    d = (re.search(r"Decided:?\s*([A-Z][a-z]+\.? \d{1,2},? \d{4})", head)
         or re.search(r"OPINION ISSUED:\s*([A-Z][a-z]+\.? \d{1,2},? \d{4})", head)
         or re.search(r"ENTERED BY ORDER OF THE COURT\s*([A-Z][a-z]+\.? \d{1,2},? \d{4})", head))
    origin = ""
    m = re.search(r"(?:Appeal|Appeals|Petition|Petitions) (?:for review )?from (?:the )?(.{0,200})", head)
    src = m.group(1) if m else head[:3000]
    for code, pat in ORIGINS:
        if re.search(pat, src):
            origin = code; break
    return {
        "decided": d.group(1) if d else "",
        "precedential": "Nonprecedential" if re.search(r"This disposition is nonprecedential", head, re.I) else "Precedential",
        "origin_from_text": origin,
    }
