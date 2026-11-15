"""Side-by-side review workbook for the classification test (step 2).

  python3 scripts/build_review.py [--sample samples/classification_test_50.csv]

Reads results/<sample>_<model>.jsonl for each model and writes
review/<sample>_review.xlsx with four sheets:
  Summary     - cost, failures, X99 share, agreement between the models and with the text rules
  Cases       - one row per case, both models' codings next to each other, columns for the owner
  Issues      - one row per issue per model, with columns for the owner to mark right/wrong
  Cross-check - panel, author and dissent disagreements with the text rules
"""
import argparse, csv, glob, gzip, json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5"]
SHORT = {"claude-haiku-5-5": "Haiku", "claude-sonnet-5-5": "Sonnet"}
# Standard $/million tokens (input, output); batch = 50% off; cache read = 10% of input,
# cache write = 125%. Haiku charges 5x for a request over 100K input tokens.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00)}
FAVORED = {"side_a": "Side A", "side_b": "Side B", "mixed": "mixed", "other_unclear": "other/unclear"}
BOLD = Font(bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")
DIFF = PatternFill("solid", fgColor="FCE4D6")   # orange: the models disagree
OWNER = PatternFill("solid", fgColor="E2EFDA")  # green: columns for the owner to fill in


def norm(name):
    return name.upper().replace("\u2019", "'").replace("CHIEF JUDGE", "").replace("(VISITING)", "").strip()


def request_cost(model, u):
    pin, pout = PRICES[model]
    total_in = u["input"] + u["cache_read"]
    if model == "claude-haiku-5-5" and total_in > 100_000:
        pin, pout = pin * 5, pout * 5
    return 0.5 * (u["input"] * pin + u["cache_read"] * pin * 0.1 + u["output"] * pout) / 1e6


def text_rule_dissenters(sep):
    """'concurrence: REYNA; dissent: PROST' -> {'PROST'} (dissents and partial dissents)."""
    out = set()
    for part in sep.split(";"):
        kind, _, judge = part.partition(":")
        if "dissent" in kind:
            out.add(norm(judge))
    return out


def issue_line(i, labels):
    lab = labels.get(i["code"], {})
    ruling = {"first": lab.get("a"), "second": lab.get("b")}.get(i["ruling"]) or i["ruling"]
    d = f" [dissent: {', '.join(i['dissenting_judges'])}]" if i["dissenting_judges"] else ""
    return f"{i['code']} {lab.get('issue', '')}: {ruling} -> {FAVORED[i['favored']]}, {i['disposition']}{d}"


def write_sheet(ws, header, rows, widths, owner_cols=(), diff_test=None):
    ws.append(header)
    for c in ws[1]:
        c.font = BOLD
        c.alignment = WRAP
    for r in rows:
        ws.append(r)
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = WRAP
        if diff_test and diff_test(row):
            for c in row:
                c.fill = DIFF
        for oc in owner_cols:
            row[oc].fill = OWNER
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions


def archive_opinion_chars():
    keys = {r["key"] for r in csv.DictReader(open(ROOT / "data/decisions.csv"))
            if r["doc_type"] == "Opinion" and "superseded" not in r["flag"]}
    seen, total = set(), 0
    for f in sorted(glob.glob(str(ROOT / "data/text/*.jsonl.gz"))):
        for line in gzip.open(f, "rt"):
            d = json.loads(line)
            if d["key"] in keys and d["key"] not in seen:
                seen.add(d["key"])
                total += len(d["text"])
    return len(seen), total


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sample", default="samples/classification_test_50.csv")
    a = p.parse_args()
    stem = Path(a.sample).stem
    cases = list(csv.DictReader(open(ROOT / a.sample)))
    # separate opinions from the current archive table (the rule was corrected after the sample was drawn)
    sep = {r["key"]: r["separate_opinions"] for r in csv.DictReader(open(ROOT / "data/decisions.csv"))}
    for c in cases:
        c["separate_opinions"] = sep.get(c["key"], c["separate_opinions"])
    labels = {i["code"]: {"issue": i["issue"], "a": i["side_a_label"], "b": i["side_b_label"], "group": i["group"]}
              for i in csv.DictReader(open(ROOT / "data/issue_list.csv"))}
    res = {}
    for m in MODELS:
        f = ROOT / "results" / f"{stem}_{m}.jsonl"
        res[m] = {json.loads(l)["id"]: json.loads(l) for l in open(f)} if f.exists() else {}
    models = [m for m in MODELS if res[m]]

    case_rows, issue_rows, xrows = [], [], []
    stats = {m: Counter() for m in models}
    agree = Counter()
    for c in cases:
        tid = c["test_id"]
        cod = {m: res[m].get(tid, {}).get("coding") for m in models}
        rule_panel = {norm(j) for j in c["panel"].split(";") if j.strip()}
        rule_author = norm(c["author"])
        rule_diss = text_rule_dissenters(c["separate_opinions"])
        for m in models:
            s, k = stats[m], cod[m]
            if not k:
                s["failed"] += 1
                continue
            s["cases"] += 1
            s["issues"] += len(k["issues"])
            s["x99"] += sum(i["code"] == "X99" for i in k["issues"])
            s["other_unclear"] += sum(i["favored"] == "other_unclear" for i in k["issues"])
            s["mixed"] += sum(i["favored"] == "mixed" for i in k["issues"])
            ai_panel = {norm(j) for j in k["panel_judges"]}
            ai_author = norm(k["author"])
            ai_diss = {norm(j) for i in k["issues"] for j in i["dissenting_judges"]}
            ok_p = ai_panel == rule_panel
            ok_a = ai_author == rule_author or (rule_author.startswith("PER CURIAM") and "PER CURIAM" in ai_author)
            ok_d = ai_diss == rule_diss
            s["panel_ok"] += ok_p
            s["author_ok"] += ok_a
            s["dissent_ok"] += ok_d
            if not (ok_p and ok_a and ok_d):
                xrows.append([tid, c["case_name"], SHORT[m],
                              "" if ok_p else f"rules: {'; '.join(sorted(rule_panel))} | AI: {'; '.join(sorted(ai_panel))}",
                              "" if ok_a else f"rules: {rule_author} | AI: {k['author']}",
                              "" if ok_d else f"rules: {', '.join(sorted(rule_diss)) or 'none'} | AI: {', '.join(sorted(ai_diss)) or 'none'}",
                              c["separate_opinions"]])
            other = [o for o in models if o != m and cod[o]]
            other_codes = Counter(i["code"] for o in other for i in cod[o]["issues"])
            for i in k["issues"]:
                lab = labels.get(i["code"], {})
                ruling = {"first": lab.get("a"), "second": lab.get("b")}.get(i["ruling"]) or i["ruling"]
                issue_rows.append([tid, c["case_name"], SHORT[m], i["code"], lab.get("issue", ""), ruling,
                                   FAVORED[i["favored"]], i["disposition"], ", ".join(i["dissenting_judges"]),
                                   "yes" if other_codes.get(i["code"]) else "NO" if other else "",
                                   i["description"], i["quote"], "", ""])
        both = [cod[m] for m in models]
        if len(models) == 2 and all(both):
            h, s_ = both
            agree["cases"] += 1
            agree["case_type"] += h["case_type"] == s_["case_type"]
            hc, sc = Counter(i["code"] for i in h["issues"]), Counter(i["code"] for i in s_["issues"])
            agree["same_codes"] += hc == sc
            agree["codes_h"] += sum(hc.values())
            agree["codes_s"] += sum(sc.values())
            agree["codes_shared"] += sum((hc & sc).values())
            # favored side on codes both models used exactly once
            for code in hc & sc:
                if hc[code] == 1 and sc[code] == 1:
                    fh = next(i["favored"] for i in h["issues"] if i["code"] == code)
                    fs = next(i["favored"] for i in s_["issues"] if i["code"] == code)
                    agree["fav_pairs"] += 1
                    agree["fav_same"] += fh == fs
        row = [tid, c["case_name"], c["pdf_url"], c["group"], c["origin"], c["precedential"],
               c["separate_opinions"]]
        for m in models:
            k = cod[m]
            row += [k["case_type"], "\n".join(issue_line(i, labels) for i in k["issues"]) or "(no issues)"] if k \
                else ["FAILED", res[m].get(tid, {}).get("status", "missing")]
        row += [""] * (len(models) + 1)
        case_rows.append(row)

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    n_arch, chars_arch = archive_opinion_chars()
    chars_test = sum(int(c["chars"]) for c in cases)
    lines = [["Classification test: " + stem], [],
             ["", *[SHORT[m] for m in models]]]
    def line(label, f):
        lines.append([label, *[f(m) for m in models]])
    line("Cases coded", lambda m: stats[m]["cases"])
    line("Failed requests", lambda m: stats[m]["failed"])
    line("Issues coded", lambda m: stats[m]["issues"])
    line("Issues per case", lambda m: round(stats[m]["issues"] / max(stats[m]["cases"], 1), 2))
    line("X99 'Other' share (>5% = a code is missing)",
         lambda m: f"{stats[m]['x99'] / max(stats[m]['issues'], 1):.1%}")
    line("'other/unclear' share", lambda m: f"{stats[m]['other_unclear'] / max(stats[m]['issues'], 1):.1%}")
    line("'mixed' share", lambda m: f"{stats[m]['mixed'] / max(stats[m]['issues'], 1):.1%}")
    line("Panel matches text rules", lambda m: f"{stats[m]['panel_ok']} of {stats[m]['cases']}")
    line("Author matches text rules", lambda m: f"{stats[m]['author_ok']} of {stats[m]['cases']}")
    line("Dissenters match text rules", lambda m: f"{stats[m]['dissent_ok']} of {stats[m]['cases']}")
    costs = {m: sum(request_cost(m, r["usage"]) for r in res[m].values() if "usage" in r) for m in models}
    line("Test cost (batch rate, estimate)", lambda m: f"${costs[m]:.2f}")
    # Scale to the archive: input by text length, output and the cached system prompt per case.
    def archive(m):
        rs = [r for r in res[m].values() if "usage" in r]
        pin, pout = PRICES[m]
        inp = sum(r["usage"]["input"] for r in rs) * pin * 0.5 / 1e6
        per_case = sum(r["usage"]["cache_read"] * pin * 0.05 + r["usage"]["output"] * pout * 0.5 for r in rs) / 1e6 / len(rs)
        return f"${inp * chars_arch / chars_test + per_case * n_arch:,.0f}"
    line(f"Full archive estimate ({n_arch:,} opinions)", archive)
    if agree["cases"]:
        lines += [[], ["Agreement between the two models", f"(on {agree['cases']} cases both coded)"],
                  ["Same case type", f"{agree['case_type']} of {agree['cases']}"],
                  ["Exactly the same issue codes", f"{agree['same_codes']} of {agree['cases']}"],
                  ["Issue codes used by both", f"{agree['codes_shared']} (Haiku {agree['codes_h']}, Sonnet {agree['codes_s']})"],
                  ["Same side favored, where both used a code once", f"{agree['fav_same']} of {agree['fav_pairs']}"]]
    lines += [[], ["How to review"],
              ["Cases sheet: both models side by side; orange rows = the models coded different issue codes. "
               "Green columns are for you."],
              ["Issues sheet: one row per issue. 'Other model has code' = NO marks issues only one model found. "
               "Mark 'Correct?' Y/N for each, and say what is wrong in 'Your notes'."],
              ["Cross-check sheet: where an AI's panel, author or dissenters differ from the text rules "
               "(usually the AI is wrong; a text-rule error would be worth knowing)."],
              ["Archive estimate: input scaled by text length (the test over-represents long, precedential and "
               "dissent cases), output and cached instructions per case."]]
    for l in lines:
        ws.append(l)
    ws["A1"].font = BOLD
    ws.column_dimensions["A"].width = 48
    for col in "BC":
        ws.column_dimensions[col].width = 22

    hdr = ["Test", "Case", "PDF", "Test group", "Origin", "Precedential", "Separate opinions (text rules)"]
    widths = [6, 30, 12, 18, 8, 10, 18]
    for m in models:
        hdr += [f"{SHORT[m]}: case type", f"{SHORT[m]}: issues -> side favored"]
        widths += [22, 60]
    hdr += [f"Your verdict: {SHORT[m]} right? (Y/N/partly)" for m in models] + ["Your notes"]
    widths += [12] * len(models) + [40]
    n_fixed = 7
    def differs(row):
        if len(models) < 2:
            return False
        a_, b_ = row[n_fixed + 1].value or "", row[n_fixed + 3].value or ""
        codes = lambda t: sorted(l.split(" ")[0] for l in t.split("\n") if l)
        return codes(a_) != codes(b_)
    ws = wb.create_sheet("Cases")
    owner_cols = range(len(hdr) - len(models) - 1, len(hdr))
    write_sheet(ws, hdr, case_rows, widths, owner_cols, differs)
    for row in ws.iter_rows(min_row=2):
        url = row[2].value
        row[2].value, row[2].hyperlink, row[2].style = "open PDF", url, "Hyperlink"
        row[2].alignment = WRAP
        if differs(row):
            row[2].fill = DIFF

    ws = wb.create_sheet("Issues")
    write_sheet(ws, ["Test", "Case", "Model", "Code", "Issue", "Ruling", "Favored", "Disposition", "Dissenting",
                     "Other model has code", "Description", "Quote", "Correct? (Y/N)", "Your notes"],
                issue_rows, [6, 26, 8, 6, 24, 16, 11, 14, 10, 10, 50, 50, 10, 30], (12, 13),
                lambda row: row[9].value == "NO")

    ws = wb.create_sheet("Cross-check")
    write_sheet(ws, ["Test", "Case", "Model", "Panel differs", "Author differs", "Dissenters differ",
                     "Separate opinions (text rules)"], xrows, [6, 30, 8, 40, 30, 40, 24])

    out = ROOT / "review" / f"{stem}_review.xlsx"
    out.parent.mkdir(exist_ok=True)
    wb.save(out)
    print(f"saved {out.relative_to(ROOT)}")
    for l in lines[2:17]:
        print("  ", *l)


if __name__ == "__main__":
    main()
