"""Pick the 50 decisions for the AI classification test.

Design (agreed with the owner 2026-11-15): 35 patent cases, 15 other, spread so that every
side definition is tested. Within each group, cases are drawn at random (fixed seed), except
that some patent slots are reserved for opinions with a dissent or partial dissent (to test
per-issue dissent coding) and one for an en banc decision. About half of each patent group is
precedential. Decisions with no panel, superseded opinions and 2-judge panels are left out.

Usage: python3 scripts/select_test_sample.py   ->  samples/classification_test_50.csv
"""
import csv, glob, gzip, json, random, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 20261115

# group: (number of cases, how many of them reserved for dissents)
PLAN = {
    "PTAB trial or inter partes reexam": (13, 3),
    "PTO ex parte appeal or ex parte reexam": (5, 1),
    "District court patent": (14, 3),
    "ITC": (3, 0),
    "TTAB trademark": (2, 0),
    "Veterans": (3, 0),
    "Federal employment": (3, 0),
    "Court of Federal Claims": (3, 0),
    "Board of Contract Appeals": (1, 0),
    "Court of International Trade": (2, 0),
    "District court non-patent": (1, 0),
}
PATENT = {"PTAB trial or inter partes reexam", "PTO ex parte appeal or ex parte reexam", "District court patent", "ITC"}
TRIAL = re.compile(r"inter partes review|post-grant review|covered business method|\b(IPR|PGR|CBM)\d{4}", re.I)


def group_of(row, text):
    o = row["origin"]
    if o == "PTO":
        head = text[:5000]
        if TRIAL.search(head) or re.search(r"inter partes reexamination|\b95/\d{3},\d{3}", head, re.I):
            return "PTAB trial or inter partes reexam"  # two-party: patent owner vs petitioner/requester
        if re.search(r"\binterference\b", head, re.I):
            return None  # interferences have no side; not tested
        return "PTO ex parte appeal or ex parte reexam"
    if o == "DCT":
        # Rough rule, used only to draw the test sample (the AI records the case type itself).
        n = len(re.findall(r"patent", text, re.I))
        return "District court patent" if n >= 5 else "District court non-patent" if n == 0 else None
    return {"ITC": "ITC", "TTAB": "TTAB trademark", "CAVC": "Veterans", "VA": "Veterans",
            "MSPB": "Federal employment", "ARB": "Federal employment", "OCWR": "Federal employment",
            "CFC": "Court of Federal Claims", "BCA": "Board of Contract Appeals",
            "CIT": "Court of International Trade"}.get(o)


def main():
    rows = {r["key"]: r for r in csv.DictReader(open(ROOT / "data/decisions.csv"))}
    text = {}
    for f in sorted(glob.glob(str(ROOT / "data/text/*.jsonl.gz"))):
        for line in gzip.open(f, "rt"):
            d = json.loads(line)
            text.setdefault(d["key"], d["text"])  # the text cache holds a few duplicate entries

    pools = {g: [] for g in PLAN}
    en_banc = []
    for k in sorted(rows):
        r = rows[k]
        if r["doc_type"] != "Opinion" or k not in text:
            continue
        if re.search(r"panel not found|superseded|2-judge", r["flag"]):
            continue
        g = group_of(r, text[k])
        if g is None:
            continue
        if "en banc" in r["flag"]:
            if g in PATENT:
                en_banc.append((g, k))
            continue
        pools[g].append(k)

    rng = random.Random(SEED)
    picked = []  # (group, key, reason)
    eb_group, eb_key = rng.choice(en_banc)
    picked.append((eb_group, eb_key, "en banc"))
    for g, (n, n_dissent) in PLAN.items():
        pool = pools[g][:]
        rng.shuffle(pool)
        taken = [k for gg, k, _ in picked if gg == g]
        n_left = n - len(taken)
        dissents = [k for k in pool if "dissent" in rows[k]["separate_opinions"].lower()][:n_dissent]
        picked += [(g, k, "dissent") for k in dissents]
        rest = [k for k in pool if k not in dissents]
        need = n_left - len(dissents)
        if g in PATENT:  # about half precedential
            prec = [k for k in rest if rows[k]["precedential"] == "Precedential"]
            nonp = [k for k in rest if rows[k]["precedential"] != "Precedential"]
            n_prec = max(0, (n + 1) // 2 - sum(rows[k]["precedential"] == "Precedential"
                                               for gg, k, _ in picked if gg == g))
            n_prec = min(n_prec, need)
            chosen = prec[:n_prec] + nonp[:need - n_prec]
        else:
            chosen = rest[:need]
        picked += [(g, k, "random") for k in chosen]

    out = ROOT / "samples/classification_test_50.csv"
    cols = ["test_id", "group", "selected_as", "case_name", "appeal_numbers", "decided_iso", "origin",
            "precedential", "panel", "author", "separate_opinions", "argued", "chars", "pdf_url", "key"]
    order = list(PLAN)
    picked.sort(key=lambda x: (order.index(x[0]), rows[x[1]]["decided_iso"]))
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, (g, k, why) in enumerate(picked, 1):
            r = rows[k]
            w.writerow([f"T{i:02d}", g, why, r["case_name"], r["appeal_numbers"], r["decided_iso"], r["origin"],
                        r["precedential"], r["panel"], r["author"], r["separate_opinions"], r["argued"],
                        len(text[k]), r["pdf_url"], k])
    print(f"wrote {len(picked)} cases to {out.relative_to(ROOT)}")
    print("pool sizes:", {g: len(p) for g, p in pools.items()}, "en banc (patent):", len(en_banc))


if __name__ == "__main__":
    main()
