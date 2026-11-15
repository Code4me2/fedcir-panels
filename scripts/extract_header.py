"""Extract panel, author, and separate opinions from Federal Circuit opinion text (free text rules, no AI)."""
import re

TITLE = r"(?:Chief|Circuit|Senior Circuit|District|Senior District|Chief District|Senior|Judge)"
NAME = r"[A-Z][A-Z'\-]+(?: [A-Z][A-Z'\-]+)?"

def norm(t):
    t = t.replace("’", "'").replace(" ", " ")
    return re.sub(r"[ \t]+", " ", t)

TITLE_PHRASE = r"(?:Chief|Circuit|Senior Circuit|Senior|District|Chief District|Senior District)?\s*(?:Judges?|Justice)\b\.?[\*∗]?"

def split_names(raw):
    """Turn 'PROST, Chief Judge, LOURIE and DYK, Circuit Judges, and FOGEL, District Judge' into names.
    Visiting judges are tagged so a district judge MOORE is not confused with Chief Judge MOORE."""
    raw = re.sub(r"^\s*Before[,:]?\s+", "", raw)
    raw = re.sub(r"\b([A-Z]) ([A-Z]{2,})\b", r"\1\2", raw)   # letter-spaced small caps: "D YK" -> "DYK"
    parts = re.split(rf"(,?\s*{TITLE_PHRASE})", raw)
    names = []
    for chunk, title in zip(parts[0::2], parts[1::2] + [""]):
        tag = " (visiting)" if ("District" in title or "Justice" in title) else ""
        for n in re.split(r",|\b[Aa][Nn][Dd]\b", chunk):
            n = n.strip(" .*∗,0123456789†‡")
            if re.fullmatch(NAME, n): names.append(n + tag)
    return names

def parse_panel(text):
    """Return list of judge surnames from the 'Before ...' line, or a Rule 36 'PER CURIAM (...)' line."""
    if re.search(r"Fed\.\s*Cir\.\s*R\.\s*36", text):
        r36 = re.search(r"PER\s?C\s?URIAM\s*\((.{5,250}?)(?:\)|(?=AFFIRMED))", text, re.S)
        if r36:
            raw = re.sub(r"\s+", " ", r36.group(1))
            return split_names(raw), raw
    for m in re.finditer(r"\bBefore[,:]?\s+(?=[A-Z][A-Za-z']+,? )(.{5,600}?(?:Judges?|Justice)\s?[\*∗\d†‡]*(?:\.|(?=\s*\n)))", text, re.S):
        raw = re.sub(r"\s+", " ", m.group(1))
        if not re.match(r"[A-Z][A-Z']", raw):  # mixed-case line ("Before Prost, Chief Judge, ..."): accept only if it is names and titles
            leftover = re.sub(rf"{TITLE_PHRASE}|\b(?:and|And)\b|[A-Z][a-z'\-]+(?: [A-Z][a-z'\-]+)?|[,.\s\*∗\d]", "", raw)
            if leftover or len(raw) > 250: continue
            raw = raw.upper().replace(" AND ", " and ")
            raw = re.sub(r"\b(CHIEF|CIRCUIT|SENIOR|DISTRICT|JUDGES?|JUSTICE)\b", lambda t: t.group(1).title(), raw)
        parse_panel.end = m.end()
        return split_names(raw), raw
    return None, None

def parse_author(text, panel_end):
    after = text[panel_end:panel_end + 3000]
    if re.search(r"Opinion for the court filed\s+PER CURIAM|^\s*PER CURIAM\.?\s*$", after, re.M | re.I):
        return "PER CURIAM"
    m = re.search(rf"Opinion for the court filed by\s+(?:{TITLE}\s+)*Judges?\s+({NAME})", re.sub(r"\s+", " ", after))
    if m:
        return m.group(1)
    # "CHEN, Circuit Judge." / "CHEN, Circuit Judge, Securus appeals" / "O'Malley, Circuit Judge." -- but not a list of joining judges
    m = re.search(rf"^\s*({NAME}|[A-Z][A-Za-z'\-]+),\s*(?i:(?:Chief |Circuit |Senior Circuit |District |Chief District |Senior District )?Judge)"
                  rf"(?:\s?[.:]|,(?!\s*[A-Z][A-Z'\-]+(?:,| and))|\s*$)", after, re.M)
    return m.group(1).upper() if m else None

def parse_separate(text):
    flat = re.sub(r"\s+", " ", text[:8000])
    out = []
    for m in re.finditer(rf"((?:Opinion )?(?:[Cc]oncurring|[Dd]issenting|[Cc]oncurring in part and dissenting in part|[Dd]issenting in part)[a-z ]*?) (?:opinion )?filed by (?:{TITLE} )*Judges? ([A-Z][A-Z'\-]+)", flat):
        kind = "dissent" if "issent" in m.group(1) else "concurrence"
        if "oncurring in part and dissenting" in m.group(1): kind = "partial dissent"
        out.append(f"{kind}: {m.group(2)}")
    return sorted(set(out))

def extract(text):
    text = norm(text)
    if re.search(r"AFFIRMED\.\s*See Fed\.\s*Cir\.\s*R\.\s*36", text):
        panel, raw = parse_panel(text)
        return {"panel": panel, "panel_raw": raw, "author": "PER CURIAM (RULE 36)", "separate_opinions": []}
    parse_panel.end = 0
    panel, raw = parse_panel(text)
    end = parse_panel.end
    return {
        "panel": panel,
        "panel_raw": raw,
        "author": parse_author(text, end) if raw else None,
        "separate_opinions": parse_separate(text),
    }


ORIGINS = [
    ("TTAB", r"Trademark Trial and Appeal Board"),   # before PTO: TTAB appeals also name the Patent and Trademark Office
    ("PTO", r"Patent and Trademark Office|Patent Trial and Appeal Board|Board of Patent Appeals"),
    ("ITC", r"International Trade Commission"),
    ("DCT", r"United States District Court"),
    ("CFC", r"Court of Federal Claims"),
    ("CAVC", r"Court of Appeals for Veterans Claims"),
    ("MSPB", r"Merit Systems Protection"),
    ("CIT", r"Court of International Trade"),
    ("BCA", r"Board of Contract Appeals"),
    ("ARB", r"[Aa]rbitrat"),
]

def extract_more(text):
    text = norm(text)
    head = re.sub(r"\s+", " ", text[:6000])
    d = (re.search(r"Decided:?\s*([A-Z][a-z]+\.? \d{1,2},? \d{4})", head)
         or re.search(r"OPINION ISSUED:\s*([A-Z][a-z]+\.? \d{1,2},? \d{4})", head)
         or re.search(r"ENTERED BY ORDER OF THE COURT\s*([A-Z][a-z]+\.? \d{1,2},? \d{4})", head)
         or re.search(r"Filed: (\d{2}/\d{2}/\d{4})", head))   # court's filing stamp, used when the text gives no date
    origin = ""
    # The caption line: "Appeal from …", "Petition for review of …" (MSPB, arbitrators),
    # "On Petition for Writ of Mandamus to …".
    m = re.search(r"(?:Appeal|Appeals|Petition|Petitions) (?:for review |for (?:a )?Writ of Mandamus )?(?:from|of|to) (?:the )?(.{0,200})", head)
    if m:
        for code, pat in ORIGINS:
            if re.search(pat, m.group(1)):
                origin = code; break
    r = None
    if not origin:  # direct petitions against an agency (VA rules, DOJ benefits, congressional workplace, GAO)
        r = re.search(r"v\. ([A-Z][A-Z ,.'&]+?), (?:Respondent|Cross-Applicant)", head)
        if r:
            agency = r.group(1)
            origin = ("VA" if "VETERANS" in agency else "DOJ" if "JUSTICE" in agency else
                      "OCWR" if re.search(r"COMPLIANCE|CONGRESSIONAL WORKPLACE", agency) else
                      "GAO" if "ACCOUNTABILITY" in agency else "")
    if not origin and not m:
        # No caption line: scan the first page. District court goes last, because a visiting
        # district judge's "sitting by designation" footnote names a United States District Court.
        for code, pat in [o for o in ORIGINS if o[0] != "DCT"] + [o for o in ORIGINS if o[0] == "DCT"]:
            if re.search(pat, head[:3000]):
                origin = code; break
    if not origin and re.search(r"Office of Compliance|Office of Congressional Workplace Rights", head[:3000]):
        origin = "OCWR"
    if not origin and r:
        origin = "AGENCY"
    return {
        "decided": d.group(1) if d else "",
        "precedential": "Nonprecedential" if re.search(r"This disposition is nonprecedential", head, re.I) else "Precedential",
        "origin_from_text": origin,
    }
