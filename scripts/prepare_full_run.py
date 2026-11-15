"""Split the full archive of written opinions into batch-sized parts for classification.

  python3 scripts/prepare_full_run.py

Writes samples/full_v1_part<N>.csv. Every written opinion is included except those flagged
"superseded by revised opinion" (Rule 36 judgments have no reasoning to classify). Each row
gets a short stable id (O00001...) because the batch API limits request ids to 64 characters;
the result files carry both the id and the decision key.

A batch may hold at most 256 MB, and the ~19K-character instructions are repeated in every
request, so the parts are balanced by size (instructions + opinion text), about 70 MB each.
"""
import csv, glob, gzip, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTS = 4
PROMPT_CHARS = 32000  # instructions + response format, as serialized JSON (generous)
FIELDS = ["id", "key", "case_name", "appeal_numbers", "decided_iso", "origin", "precedential", "chars"]


def main():
    rows = [r for r in csv.DictReader(open(ROOT / "data/decisions.csv"))
            if r["doc_type"] == "Opinion" and "superseded" not in r["flag"]]
    rows.sort(key=lambda r: (r["decided_iso"], r["key"]))
    length = {}
    for f in sorted(glob.glob(str(ROOT / "data/text/*.jsonl.gz"))):
        for line in gzip.open(f, "rt"):
            d = json.loads(line)
            length.setdefault(d["key"], len(d["text"]))
    total = sum(length[r["key"]] + PROMPT_CHARS for r in rows)
    part, size, out = 1, 0, {i: [] for i in range(1, PARTS + 1)}
    for n, r in enumerate(rows, 1):
        r = {**r, "id": f"O{n:05d}", "chars": length[r["key"]]}
        if size > total * part / PARTS and part < PARTS:
            part += 1
        out[part].append(r)
        size += r["chars"] + PROMPT_CHARS
    for p, rs in out.items():
        path = ROOT / f"samples/full_v1_part{p}.csv"
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rs)
        mb = sum(r["chars"] + PROMPT_CHARS for r in rs) / 1e6
        print(f"{path.relative_to(ROOT)}: {len(rs)} opinions, {rs[0]['decided_iso']} to {rs[-1]['decided_iso']}, ~{mb:.0f} MB")


if __name__ == "__main__":
    main()
