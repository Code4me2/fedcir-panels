"""Draw a random sample of AI-coded issues from the full run for the owner to check by hand.

  python3 scripts/draw_accuracy_check.py [--n 25] [--seed 20261115] [--scope patent|all]

Writes review/accuracy_check_v1.xlsx: one row per issue with the case, a link to the opinion, the
parties on each side, the code, the ruling in the issue's own words, the side favored, dissenters,
the AI's description and supporting quote, and empty "Correct? (Y/N)" and "Notes" columns.
Default scope: issues in patent cases (district court/ITC, PTAB trials, ex parte), X99 excluded.
The result ("23 of 25 correct") goes into the methodology.
"""
import argparse, csv, glob, json, random
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parent.parent
FULL = "results/full_v1_part*_claude-haiku-5-5.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--seed", type=int, default=20261115)
    ap.add_argument("--scope", choices=["patent", "all"], default="patent")
    a = ap.parse_args()
    dec = {r["key"]: r for r in csv.DictReader(open(ROOT / "data/decisions.csv"))}
    issues = {i["code"]: i for i in csv.DictReader(open(ROOT / "data/issue_list.csv"))}
    sides = {s["case_type"]: s for s in csv.DictReader(open(ROOT / "data/sides.csv"))}
    pool = []
    for f in sorted(glob.glob(str(ROOT / FULL))):
        for line in open(f):
            r = json.loads(line)
            c = r.get("coding")
            if not c or (a.scope == "patent" and not c["case_type"].startswith("Patent")):
                continue
            for i in c["issues"]:
                if i["code"] != "X99":
                    pool.append((r, i))
    random.seed(a.seed)
    sample = random.sample(pool, a.n)
    sample.sort(key=lambda x: dec[x[0]["key"]]["decided_iso"])

    wb = Workbook()
    ws = wb.active
    ws.title = "Check"
    head = ["#", "Decided", "Case", "Appeal", "Opinion (PDF)", "Prec.", "Panel", "Case type (AI)", "Side A (AI)",
            "Side B (AI)", "Issue", "Ruling", "Favored", "Disposition", "Dissenting", "AI description", "Supporting quote",
            "Correct? (Y/N)", "Notes"]
    ws.append(head)
    for n, (r, i) in enumerate(sample, 1):
        d, c = dec[r["key"]], r["coding"]
        iss = issues[i["code"]]
        label = {"first": iss["side_a_label"], "second": iss["side_b_label"]}.get(i["ruling"], "neither / mixed")
        s = sides[c["case_type"]]
        fav = {"side_a": "Side A: " + s["side_a"], "side_b": "Side B: " + s["side_b"],
               "mixed": "mixed", "other_unclear": "other/unclear"}[i["favored"]]
        ws.append([n, d["decided_iso"], d["case_name"], d["appeal_numbers"], d["pdf_url"], d["precedential"][:3] + ".",
                   d["panel"], c["case_type"], c["side_a_parties"], c["side_b_parties"], f'{i["code"]} {iss["issue"]}',
                   label or "-", fav, i["disposition"], ", ".join(i["dissenting_judges"]), i["description"], i["quote"], "", ""])
        ws.cell(row=n + 1, column=5).hyperlink = d["pdf_url"]
    widths = [4, 11, 28, 10, 14, 6, 22, 22, 22, 22, 24, 18, 22, 14, 12, 50, 50, 10, 30]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w
    for row in ws.iter_rows(min_row=1):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in ws[1]:
        cell.font = Font(bold=True)
    green = PatternFill("solid", fgColor="E2F0D9")
    for row in ws.iter_rows(min_row=1, min_col=18, max_col=19):
        for cell in row:
            cell.fill = green
    ws.freeze_panes = "C2"
    out = ROOT / "review/accuracy_check_v1.xlsx"
    wb.save(out)
    print(f"{out.relative_to(ROOT)}: {a.n} issues drawn from {len(pool)} ({a.scope}, seed {a.seed})")


if __name__ == "__main__":
    main()
