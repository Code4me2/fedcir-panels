"""One-time check: are opinions spread among a session's three judges more evenly than chance?

Question behind it: the dashboard could list, for a pending case, which judges have written fewer opinions in
its session so far. That is only worth showing if the court actually evens out authorship within a session.

Method (CLAUDE.md, "Session authorship check"):
- A session here = decisions with the same argument date (from the recordings) and the same 3-judge panel.
  Only argued cases with a known argument date; not en banc, not superseded. Sessions are formed in this
  script only; nothing is written to the site data.
- A signed opinion = a written opinion whose author is a panel judge (not per curiam, not Rule 36).
- Sessions with 3 or more signed opinions are tested.
- Null model: each signed opinion's author drawn at random from the three panel judges (equal chance),
  independently. 20,000 simulations.
- Statistics: (1) evenness = sum over sessions of the squared per-judge counts (lower = more even);
  (2) share of sessions where one judge wrote more than their even share (max count > ceil(k/3));
  (3) prediction test: taking each session's opinions in decision-date order, how often the author of the
  next opinion is one of the judges with the fewest opinions so far, against the chance rate.
- Run again at the week level (same panel, argument dates in the same Monday-to-Friday week) as a
  sensitivity check, since a panel often sits several days in a row.

Usage: python3 scripts/analyze_session_authorship.py
"""
import json
import math
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 20261117
SIMS = 20000


def load():
    A = json.load(open(ROOT / "docs/data/archive.json"))
    F = {k: i for i, k in enumerate(A["decision_fields"])}
    return A, F


def sessions(A, F, level):
    groups = defaultdict(list)
    for d in A["decisions"]:
        arg = d[F["argued"]]
        if len(arg) != 10 or d[F["en_banc"]] or d[F["superseded"]] or len(d[F["panel"]]) != 3:
            continue
        if level == "week":
            dt = date.fromisoformat(arg)
            key_date = (dt - timedelta(days=dt.weekday())).isoformat()
        else:
            key_date = arg
        groups[(key_date, tuple(sorted(d[F["panel"]])))].append(d)
    return groups


def summarize(A, F, level, rng):
    groups = sessions(A, F, level)
    tested = []   # (panel, [authors in decision order])
    all_sessions = len(groups)
    decs = sum(len(v) for v in groups.values())
    for (k, panel), ds in groups.items():
        ds.sort(key=lambda d: d[F["date"]])
        authors = [d[F["author"]] for d in ds if not d[F["rule36"]] and d[F["author"]] in panel]
        if len(authors) >= 3:
            tested.append((panel, authors))

    def sumsq(panel, authors):
        return sum(authors.count(j) ** 2 for j in panel)

    def lopsided(panel, authors):
        return max(authors.count(j) for j in panel) > math.ceil(len(authors) / 3)

    obs_ss = sum(sumsq(p, a) for p, a in tested)
    obs_lop = sum(lopsided(p, a) for p, a in tested)
    # Prediction test on the real order of decisions
    hits = exp = trials = 0
    for p, a in tested:
        for i in range(1, len(a)):
            cnt = {j: a[:i].count(j) for j in p}
            low = min(cnt.values())
            fewest = [j for j in p if cnt[j] == low]
            trials += 1
            hits += a[i] in fewest
            exp += len(fewest) / 3

    sim_ss, sim_lop, sim_hits = [], [], []
    for _ in range(SIMS):
        ss = lop = h = 0
        for p, a in tested:
            r = [rng.choice(p) for _ in a]
            ss += sumsq(p, r)
            lop += lopsided(p, r)
            for i in range(1, len(r)):
                cnt = {j: r[:i].count(j) for j in p}
                low = min(cnt.values())
                h += cnt[r[i]] == low
        sim_ss.append(ss); sim_lop.append(lop); sim_hits.append(h)

    # Realistic version of the prediction test, as the dashboard would use it: every session with 2+ signed
    # opinions; for each signed opinion, count only opinions issued on an EARLIER date; skip when the three
    # judges are tied (the page would mark no one). Hit = author was among the judges marked "fewer so far".
    r_hits = r_exp = r_trials = 0
    for (k, panel), ds in groups.items():
        signed = [(d[F["date"]], d[F["author"]]) for d in ds if not d[F["rule36"]] and d[F["author"]] in panel]
        if len(signed) < 2:
            continue
        for dt, au in signed:
            cnt = {j: sum(1 for d2, a2 in signed if d2 < dt and a2 == j) for j in panel}
            low = min(cnt.values())
            fewest = [j for j in panel if cnt[j] == low]
            if len(fewest) == 3:
                continue
            r_trials += 1
            r_hits += au in fewest
            r_exp += len(fewest) / 3

    mean = lambda xs: sum(xs) / len(xs)
    print(f"\n[{level}] Dashboard-style test (2+ signed, earlier dates only, ties skipped): author was a judge marked "
          f"'fewer so far' in {r_hits} of {r_trials} ({r_hits / r_trials:.0%}); chance {r_exp / r_trials:.0%}")
    sizes = defaultdict(int)
    for p, a in tested:
        sizes[min(len(a), 6)] += 1
    # Per size: share of sessions perfectly even (every judge within 1 of the others), observed vs chance
    even_obs = sum(max(a.count(j) for j in p) - min(a.count(j) for j in p) <= 1 for p, a in tested)
    print(f"\n=== Level: {level} ===")
    print(f"Sessions formed: {all_sessions} ({decs} decisions); tested (3+ signed opinions): {len(tested)}, "
          f"{sum(len(a) for _, a in tested)} signed opinions; by size {dict(sorted(sizes.items()))} (6 = 6+)")
    print(f"Evenness (sum of squared counts): observed {obs_ss}, chance mean {mean(sim_ss):.0f}; "
          f"share of simulations as even or more even: {sum(s <= obs_ss for s in sim_ss) / SIMS:.4f}")
    print(f"Sessions where one judge wrote more than an even share: observed {obs_lop} of {len(tested)} "
          f"({obs_lop / len(tested):.0%}), chance {mean(sim_lop):.0f} ({mean(sim_lop) / len(tested):.0%}); "
          f"simulations with this few or fewer: {sum(s <= obs_lop for s in sim_lop) / SIMS:.4f}")
    print(f"Sessions with counts within 1 of each other: observed {even_obs} of {len(tested)} ({even_obs / len(tested):.0%})")
    print(f"Prediction test: next opinion written by a judge with the fewest so far: {hits} of {trials} "
          f"({hits / trials:.0%}); chance {exp:.0f} ({exp / trials:.0%}); "
          f"simulations with this many or more: {sum(s >= hits for s in sim_hits) / SIMS:.4f}")
    return tested


def main():
    A, F = load()
    rng = random.Random(SEED)
    for level in ("day", "week"):
        summarize(A, F, level, rng)


if __name__ == "__main__":
    main()
