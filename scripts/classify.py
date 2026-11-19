"""AI classification of issues and outcomes (step 2).

Reads the approved issue list (data/issue_list.csv) and side definitions (data/sides.csv),
sends each opinion to Claude through the Message Batches API (50% off), and saves one JSON
record per decision. Panel, author, date, origin etc. still come from the text rules; the AI
re-reads panel and author only so the two can be cross-checked.

  python3 scripts/classify.py dry-run  --sample samples/classification_test_50.csv
  python3 scripts/classify.py submit   --sample samples/classification_test_50.csv --model claude-haiku-5-5
  python3 scripts/classify.py collect  --model claude-haiku-5-5      (waits, then saves results)

The API key is read from FEDCIR_API_KEY (or ANTHROPIC_API_KEY). Requests always go to
https://api.anthropic.com, the owner's own account, whatever ANTHROPIC_BASE_URL says.
"""
import argparse, csv, glob, gzip, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work" / "classify"
RESULTS = ROOT / "results"
API_URL = "https://api.anthropic.com"
EFFORT = "medium"
MAX_TOKENS = 16000  # thinking counts toward this; outputs are normally 1-3k tokens

# Standard prices per million tokens (input, output), from Anthropic's model table, Nov 2026.
# The batch discount (50%) is applied in the cost summary. Cache reads are ~10% of input.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00)}

DISPOSITIONS = ["affirmed", "reversed", "vacated", "vacated and remanded", "reversed and remanded",
                "affirmed in part", "dismissed", "remanded", "other"]


def load_lists():
    issues = list(csv.DictReader(open(ROOT / "data/issue_list.csv")))
    sides = list(csv.DictReader(open(ROOT / "data/sides.csv")))
    return issues, sides


def system_prompt(issues, sides):
    side_lines = "\n".join(
        f"- {s['case_type']}: Side A = {s['side_a']}; Side B = {s['side_b'] or '(none)'}"
        + (f" ({s['note']})" if s["note"] else "") for s in sides)
    groups, issue_lines = None, []
    for i in issues:
        if i["group"] != groups:
            groups = i["group"]
            issue_lines.append(f"\n{groups}")
        labels = f" [outcomes: first = {i['side_a_label']} / second = {i['side_b_label']}]" if i["side_a_label"] else ""
        issue_lines.append(f"- {i['code']} {i['issue']}: {i['covers']}{labels}")
    return f"""You code decisions of the U.S. Court of Appeals for the Federal Circuit for a public research \
dataset. The dataset shows, for each judge, how they voted on each kind of issue, by the side the vote favored, \
compared with the court as a whole. Accuracy matters more than coverage: a wrong code is worse than "other_unclear".

## Step 1: case type and sides
Pick the case type from this list by the nature of the dispute. Side A and Side B are defined per case type:
{side_lines}
For any other private-party-vs-government case (e.g. a Little Tucker Act claim in district court), use \
"Other petitions against an agency (DOJ, GAO, etc.)", with the private party as Side A. Name the actual \
parties on each side in side_a_parties and side_b_parties. Side A and Side B come only from these \
definitions, never from who appealed, who won below, or whose name comes first.

## Step 2: issues
List every issue the court actually decided, using exactly one code per issue from this list:
{chr(10).join(issue_lines)}

Rules:
- Code only issues the court decided. Skip issues it says it "need not reach" or does not address.
- Do not code the court's routine statement of its own jurisdiction (e.g. "We have jurisdiction under \
28 U.S.C. § 1295(a)(4)(A)"). Code X01 only when a party contested jurisdiction or the court itself \
analyzed a real question about it.
- Use codes from the group that fits the case type: P codes only in patent cases, T codes only in \
trademark cases, V veterans, E federal employment, C government contracts, F other Court of Federal \
Claims cases, R trade. X (procedure) codes fit any case type.
- If the court vacates or reverses because the tribunal failed to explain itself or used the wrong procedure, \
without deciding the merits, code only that procedural issue (e.g. X06), not the underlying merits issue.
- If the court holds that the tribunal applied the wrong legal standard to a merits issue, that is a ruling \
on the merits issue: use that issue's own code, not X06. \
X06 is for failures to explain, to address an argument, or to give notice.
- Vacated or remanded rulings favor the side that appealed on that issue.
- If the court refuses to consider an argument as forfeited or waived, code X04 for the side that benefits, \
not the underlying issue.
- Claim construction (P11) is coded by its effect on the judgment: e.g. a construction that leads the court \
to vacate a noninfringement judgment favors the patent owner. If the effect is unclear, or the court adopted \
a construction neither side asked for, use other_unclear.
- ruling = which of the code's two outcome labels describes the court's ruling on the issue ("first", \
"second", or "neither" for mixed or unclear results and for X99).
- favored = the side the ruling actually helped. For most codes the first outcome favors Side A, but for the \
procedure codes (X01-X11) either side may benefit (e.g. "no jurisdiction" helps whichever side argued for \
dismissal), so decide from the case. Values: side_a, side_b, "mixed" when the court ruled for each side on different claims, patents or \
counts within the same issue; "other_unclear" when the outcome on the issue favors neither side clearly \
(also for case types with no sides).
- If two distinct rulings fall under the same code (e.g. obviousness of two different patents with different \
results), list them as separate issues.
- dissenting_judges: surnames of panel judges who dissented on THIS issue. A judge who "concurs in part and \
dissents in part" is listed only for the issues the dissent covers. Concurring judges are not dissenters. Read each \
separate opinion to see which issues it disagrees with, including disagreement only about the remedy or \
relief, which is a dissent on the issue that remedy belongs to.
- Use X99 only when no code fits; say what the issue is in the description.
- quote: a short verbatim sentence from the opinion that shows the court's ruling on the issue.

## Step 3: cross-check
Give the panel judges' surnames and the authoring judge as the opinion states them ("PER CURIAM" if unsigned). \
These are compared with separate text rules, so read them from the opinion itself."""


def schema(issues, sides):
    codes = [i["code"] for i in issues]
    case_types = [s["case_type"] for s in sides]
    return {
        "type": "object",
        "properties": {
            "case_type": {"type": "string", "enum": case_types},
            "side_a_parties": {"type": "string"},
            "side_b_parties": {"type": "string"},
            "issues": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "enum": codes},
                    "description": {"type": "string"},
                    "ruling": {"type": "string", "enum": ["first", "second", "neither"]},
                    "favored": {"type": "string", "enum": ["side_a", "side_b", "mixed", "other_unclear"]},
                    "disposition": {"type": "string", "enum": DISPOSITIONS},
                    "dissenting_judges": {"type": "array", "items": {"type": "string"}},
                    "quote": {"type": "string"},
                },
                "required": ["code", "description", "ruling", "favored", "disposition", "dissenting_judges", "quote"],
                "additionalProperties": False}},
            "panel_judges": {"type": "array", "items": {"type": "string"}},
            "author": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["case_type", "side_a_parties", "side_b_parties", "issues", "panel_judges", "author", "notes"],
        "additionalProperties": False,
    }


def load_sample(path):
    rows = list(csv.DictReader(open(path)))
    want = {r["key"] for r in rows}
    text = {}
    for f in sorted(glob.glob(str(ROOT / "data/text/*.jsonl.gz"))):
        for line in gzip.open(f, "rt"):
            d = json.loads(line)
            if d["key"] in want:
                text.setdefault(d["key"], d["text"])  # the text cache has a few duplicate entries
    missing = want - set(text)
    if missing:
        sys.exit(f"no text for {len(missing)} decisions, e.g. {sorted(missing)[:3]}")
    return rows, text


def build_requests(rows, text, model, issues, sides):
    system = [{"type": "text", "text": system_prompt(issues, sides), "cache_control": {"type": "ephemeral"}}]
    fmt = {"format": {"type": "json_schema", "schema": schema(issues, sides)}, "effort": EFFORT}
    reqs = []
    for r in rows:
        user = (f"Case: {r['case_name']} (Appeal No. {r['appeal_numbers']}), decided {r['decided_iso']}, "
                f"origin code {r['origin']}.\n\nOpinion text:\n\n{text[r['key']]}")
        reqs.append({"custom_id": r.get("id") or r.get("test_id") or r["key"][:64],
                     "params": {"model": model, "max_tokens": MAX_TOKENS, "system": system,
                                "output_config": fmt, "messages": [{"role": "user", "content": user}]}})
    return reqs


KEY_VARS = ("FEDCIR_API_KEY", "ANTHROPIC_API_KEY")


def client():
    """Owner's key only. A variable named ANTHROPIC_API_KEY on the cloud environment did not reach
    the session's tools (2026-11-15), probably because Claude Code reserves that name for its own
    login, so the key is stored as FEDCIR_API_KEY instead."""
    import os, anthropic
    key = next((os.environ[v] for v in KEY_VARS if os.environ.get(v)), None)
    if not key:
        sys.exit("No API key: set FEDCIR_API_KEY on the cloud environment 'fedcir-panels' "
                 "and start a new session.")
    return anthropic.Anthropic(api_key=key, base_url=API_URL)


def cmd_dry_run(a):
    issues, sides = load_lists()
    rows, text = load_sample(a.sample)
    reqs = build_requests(rows, text, a.model, issues, sides)
    sp = reqs[0]["params"]["system"][0]["text"]
    chars = sum(len(r["params"]["messages"][0]["content"]) for r in reqs)
    print(f"{len(reqs)} requests; system prompt {len(sp):,} chars (~{len(sp)//4:,} tokens, cached); "
          f"opinions {chars:,} chars (~{chars//4:,} tokens)")
    out = WORK / "dry_run_system_prompt.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sp)
    print(f"system prompt saved to {out.relative_to(ROOT)}")


def batch_file(model, sample, tag=""):
    """Batch ids are kept in results/batches/ (committed), so a later session can collect them."""
    name = f"batch_{Path(sample).stem}_{model}{'_' + tag if tag else ''}.json"
    old = WORK / name  # the test runs kept them in work/ (not committed)
    return old if old.exists() else RESULTS / "batches" / name


def cmd_submit(a):
    issues, sides = load_lists()
    rows, text = load_sample(a.sample)
    bf = batch_file(a.model, a.sample, a.tag)
    if bf.exists():
        sys.exit(f"already submitted: {json.loads(bf.read_text())['batch_id']} (delete {bf} to resubmit)")
    reqs = build_requests(rows, text, a.model, issues, sides)
    b = client().messages.batches.create(requests=reqs)
    bf.parent.mkdir(parents=True, exist_ok=True)
    bf.write_text(json.dumps({"batch_id": b.id, "model": a.model, "sample": a.sample, "tag": a.tag, "n": len(reqs),
                              "submitted": time.strftime("%Y-%m-%d %H:%M:%S")}))
    print(f"submitted batch {b.id} ({len(reqs)} requests, {a.model})")
    return b.id


def cmd_collect(a):
    bf = batch_file(a.model, a.sample, a.tag)
    info = json.loads(bf.read_text())
    c = client()
    deadline = time.time() + 60 * a.wait if getattr(a, "wait", None) is not None else None
    while True:
        b = c.messages.batches.retrieve(info["batch_id"])
        if b.processing_status == "ended":
            break
        if deadline is not None and time.time() > deadline:
            print(f"batch {info['batch_id']} not finished yet; collect it later", flush=True)
            return None
        print(f"{time.strftime('%H:%M:%S')} {b.processing_status}: {b.request_counts.processing} still processing",
              flush=True)
        time.sleep(60)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{Path(info['sample']).stem}_{a.model}{'_' + a.tag if a.tag else ''}.jsonl"
    keys = {r.get("id") or r.get("test_id"): r["key"] for r in csv.DictReader(open(ROOT / info["sample"]))}
    tok = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    problems = []
    with open(out, "w") as f:
        for res in c.messages.batches.results(info["batch_id"]):
            rec = {"id": res.custom_id, "key": keys.get(res.custom_id, ""), "model": a.model,
                   "status": res.result.type}
            if res.result.type == "succeeded":
                m = res.result.message
                u = m.usage
                tok["input"] += u.input_tokens
                tok["cache_write"] += u.cache_creation_input_tokens or 0
                tok["cache_read"] += u.cache_read_input_tokens or 0
                tok["output"] += u.output_tokens
                rec["stop_reason"] = m.stop_reason
                rec["usage"] = {"input": u.input_tokens, "output": u.output_tokens,
                                "cache_read": u.cache_read_input_tokens or 0}
                body = next((blk.text for blk in m.content if blk.type == "text"), "")
                if m.stop_reason == "end_turn" and body:
                    rec["coding"] = json.loads(body)
                else:
                    problems.append(f"{res.custom_id}: stop_reason={m.stop_reason}")
            else:
                problems.append(f"{res.custom_id}: {res.result.type}")
            f.write(json.dumps(rec) + "\n")
    pin, pout = PRICES[a.model]
    cost = 0.5 * (tok["input"] * pin + tok["cache_write"] * pin * 1.25 + tok["cache_read"] * pin * 0.1
                  + tok["output"] * pout) / 1e6
    print(f"saved {out.relative_to(ROOT)}; tokens {tok}; estimated cost ${cost:.4f} (batch rate)")
    for p in problems:
        print("PROBLEM", p)
    return {"file": out, "cost": cost, "problems": problems}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["dry-run", "submit", "collect"])
    p.add_argument("--sample", default="samples/classification_test_50.csv")
    p.add_argument("--model", default="claude-haiku-5-5", choices=sorted(PRICES))
    p.add_argument("--tag", default="", help="label for a re-run, e.g. v2 (kept beside earlier results)")
    a = p.parse_args()
    {"dry-run": cmd_dry_run, "submit": cmd_submit, "collect": cmd_collect}[a.command](a)


if __name__ == "__main__":
    main()
