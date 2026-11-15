# Project notes: fedcir-panels

The owner is a patent attorney, new to software projects. They want a critical thinking partner: answer in chat (no separate documents unless asked), give a recommendation instead of a survey, explain technical steps in plain language, and keep moving parts to a minimum because nobody technical will maintain this. The owner will later write up the methodology from this file, so **record every method choice, rule and known limitation here** as work proceeds.

## Goal
A free, public web dashboard for Federal Circuit argument days. The court posts each panel about one hour before argument (daily schedule is posted by 9:00 a.m.). For each case the dashboard shows:
- how often the panel's judges have sat together, as pairs and as the trio;
- for the issue the user picks from a dropdown, how each judge has voted, by side, compared with the court-wide rate, with sample sizes;
- authorship share and time from argument to decision.

Why build it: per-judge outcome data exists in commercial tools, but this combines (a) panel-morning timing, (b) votes coded by side in the issue's own terms, for every judge including those joining unanimous opinions, and (c) a court-wide baseline, free and public.

## Decisions made (don't revisit without the owner)
- **Source: the court's own website, not CourtListener.** The court's PDFs are clean text. CourtListener could add pre-2015 years later.
- **Coverage starts in 2015.** The court's sitemap is ~complete from 2015 (2015: 516 vs 514 in the court's table; 2016: 543 vs 547). 2013 (~10%) and 2014 (~77%) are incomplete.
- **All case types are included**, not only patent cases. "Side" is defined per case type: patent owner vs challenger/accused infringer; veteran, employee, contractor or importer vs government.
- **Every judge's vote counts**, unanimous or not. Dissents are recorded as votes on the other side. There is no separate dissent section.
- **Votes are shown by the side they favored, in the issue's own terms** (e.g. "voted ineligible"), plus disposition (affirmed/reversed/vacated). "Appellant won" is not used on its own, because either side can be the appellant.
- **Court-wide baseline** is shown next to each judge's rate (a judge differing from the norm is the useful signal).
- **Rule 36 judgments are left out of outcome statistics (option a)** and tracked separately, e.g. as a Rule 36 rate. They are used for sit-together counts (their PDFs list the panel). Outcome labels say "in cases with written decisions".
- **The user picks the issue from a dropdown** on the dashboard. Pulling issues automatically from appeal filings is a possible future feature. Upcoming cases come from the argument calendar, not notices of appeal.
- **Panel, author, date, separate opinions, origin and precedential status come from free text rules, not AI.** AI is used only for issues and outcomes.
- **Fixed, fine-grained issue list** (merging later is free, splitting needs a re-run). Store the label, a one-sentence description and a supporting quote for each issue so later changes rarely need a re-run.
- **Claim construction is coded by its effect on the judgment**, e.g. a vacated noninfringement judgment favors the patentee. Use "other/unclear" when the effect isn't clear (including when the court did something neither side asked for); those count in n but not in percentages.
- **Argument dates:** recordings posted on bulk-upload days (more than 100 in a day: 2013-07-30, 2014-11-12, 2015-07-20, 2015-08-06, 2015-10-30) count as argued but have no date. They are excluded from time-to-decision.
- **Revised/corrected opinions replace the original** when an earlier opinion has the same appeal number(s) and panel; the original is flagged "superseded by revised opinion" and left out of stats.
- **Visiting judges are one "visiting judges" group, not rated individually** (too little data). Stark's pre-2022 panels as a Delaware district judge stay separate from his Federal Circuit record. **En banc decisions are a separate group too.** Both are still classified; the grouping is applied only in the stats/dashboard step. A later version could list a judge's en banc votes as notes.
- **Superseded decisions are excluded from stats.**
- **Decisions with no panel in the PDF (65) are left out of judge statistics** (confirmed by the owner 2026-11-15). Known gap: a January 2019 batch of Rule 36 judgments is missing from sit-together counts for that month.
- **2-judge panels (6) count toward pair counts but not trio counts** in sit-together statistics (confirmed by the owner 2026-11-15; the two judges did sit together, but there was no trio).

## Data sources (www.cafc.uscourts.gov, allowed in the cloud environment)
- **Do not bypass the court's bot-check.** The Opinions & Orders and recordings tables load from a wpDataTables admin-ajax feed behind an Azure WAF JavaScript challenge. Reading it with a headless browser was blocked as circumventing access protection. Don't do it. (The table's Excel/CSV export only covers the visible page and has no PDF links.)
- **Sitemap** (`/sitemap_index.xml`, referenced by robots.txt, which allows everything): 30 post-sitemaps, 29,409 posting URLs, listing every opinion, Rule 36 judgment and "audio-uploaded" posting. Saved in `data/sitemap/all_post_urls.txt` by `scripts/fetch_sitemap.py`. 1,198 postings dated 2025-03-10 are a re-posting of old decisions and are skipped. 71 decision URLs appear twice and are de-duplicated.
- **PDFs** are not bot-checked. Download politely: 1.5 s between requests, honest User-Agent (`fedcir-panel-research; public-records research script`).
- **RSS feeds** for ongoing updates: `/category/opinion-order/feed/` (latest ~100 postings, about 3 weeks) and `/category/oral-argument/feed/` (about 2 months). Poll weekly.
- **Calendar:** `/home/oral-argument/scheduled-cases/` links monthly PDFs (`/wp-content/uploads/OralArguments/PublicCalendar-<Month><Year>.pdf`) listing panel letter, date, courtroom, appeal number, origin, case name and [argued]/[on the briefs]. These PDFs get revised, so re-check daily before a session.
- **Panels:** `/home/oral-argument/daily-schedule/` is plain HTML, not bot-checked. The panel-name format hasn't been seen yet; first chance is the December 2026 session (starts Mon Dec 7).

## Methodology: building the archive (step 1, done 2026-11-15)
Script: `scripts/build_archive.py` (rules in `scripts/extract_header.py`). Output: `data/decisions.csv` and the full extracted text in `data/text/text_<year>.jsonl.gz`.

**Selection.** From the sitemap, take postings whose slug marks an opinion or Rule 36 judgment, posted on or after 2015-01-01, excluding the 2025-03-10 backfill, errata postings and motion-panel orders. Result: 8,023 unique decisions (6,009 opinions, 2,014 Rule 36). By decision year: 2015 659, 2016 791, 2017 747, 2018 700, 2019 707, 2020 690, 2021 652, 2022 536, 2023 556, 2024 609, 2025 739, 2026 636 (to Nov 14), plus 1 revised opinion originally decided Dec 2014.

**Locating PDFs.** The PDF address is predicted from the posting slug: `{appeal}.{opinion|rule_36_judgment}.{m-d-yyyy}.{n}.pdf` (older) or `{appeal}.{opinion|OPINION}.{m-d-yyyy}_{id}.pdf` (from ~2020; lowercase in 2020–21, uppercase later; both are tried). If neither exists, the posting page is read for its PDF link. Text is extracted with `pdftotext`.

**Text rules (no AI)** — each field, and how it is read:
- *Panel:* the "Before …, Circuit Judges." line; for Rule 36 judgments, "PER CURIAM (…)". Handles chief/senior/district titles, footnote markers, letter-spaced capitals ("D YK"), mixed case ("Before Prost, …"), a missing closing parenthesis, and uppercase "AND". Judges not on the Federal Circuit list (the 20 who sat 2015 on: Prost, Taranto, Lourie, Reyna, Dyk, Chen, Hughes, Stoll, Moore, Newman, Wallach, O'Malley, Stark, Cunningham, Bryson, Clevenger, Schall, Mayer, Linn, Plager) or titled District Judge are tagged "(visiting)"; 28 visiting judges hold 292 seats. A judge-name frequency check found no misreads.
- *Author:* "Opinion for the court filed by … Judge X", else the "X, Circuit Judge." line after the panel; "PER CURIAM" when unsigned (1,895 opinions); Rule 36 = "PER CURIAM (RULE 36)". An author name matching only a visiting judge is mapped to that judge.
- *Separate opinions:* "Concurring/Dissenting/Concurring in part and dissenting in part … filed by … Judge X" in the first 8,000 characters.
- *Decided date:* "Decided:", else "OPINION ISSUED:", else "ENTERED BY ORDER OF THE COURT <date>", else the court's "Filed: mm/dd/yyyy" stamp, else the posting date (marked "(posting date)"). `decided_iso` is the sortable form.
- *Precedential:* "This disposition is nonprecedential" → Nonprecedential (3,776 opinions), else Precedential (2,233); Rule 36 always Nonprecedential.
- *Origin:* from "Appeal/Petition … from …": TTAB 171, PTO (PTAB/BPAI/examiner) 2,182, ITC 88, district court 2,025, Court of Federal Claims 1,066, MSPB 1,041, Veterans Court 945, CIT 278, Boards of Contract Appeals 132, arbitrator 48. Direct petitions against an agency use the respondent: VA 21, DOJ 13, Office of Congressional Workplace Rights 11, GAO 1.
- *Appeal numbers:* from the slug, normalized to YY-NNNN, including consolidated numbers.
- *Argued / time to decision:* a decision is matched to "audio-uploaded" recording postings by appeal number; the argument date is the latest recording date on or before the decision date. **Assumption:** a recording's posting date is its argument date (recordings are normally posted the same day); bulk-upload days give "yes (date unknown)". Results: 5,279 with an argument date, 359 argued with unknown date, 2,385 not argued (submitted on the briefs). For opinions with dates (n = 3,442): median 69 days from argument to decision, 90th percentile 190, max 805.

**Flags** (column `flag`; 1–3% of decisions):
- 65 "panel not found": the PDF has no panel (mostly unsigned pro se per curiam opinions, and a January 2019 batch of Rule 36 judgments whose panel is only a signature image). 63 "author" are mostly the same decisions. Excluded from judge stats rather than adding another source.
- 23 "en banc"; 6 "2-judge panel" (genuine: a judge died or recused); 4 "superseded by revised opinion"; 5 "appeal number" (2009-style or miscellaneous-docket numbers like 2015-145); 1 "origin"; 1 "decided before 2015" (a 2015 re-issue of a 2014 opinion, kept).
- 76 appeals have 2+ opinions (Supreme Court remands, en banc rehearings, second appeals). These are real separate rulings and count separately, except revised re-issues (above).

**Re-running.** `python3 scripts/build_archive.py --extract-only` re-applies the rules to the saved text with no downloads (rebuilds `work/text/` from `data/text/` in a fresh session; tested to reproduce the CSV exactly). Without `--extract-only` it downloads anything missing (resumable). `--no-push` skips the GitHub commit. Background jobs are capped at 2 hours; ask the owner before relaunching a job that hit the cap.

**Test samples** (in `samples/`): 40 recent decisions from RSS, and 98 decisions stratified 7 per year 2013–2026 (seed 20261114), used to develop the rules before the full run.

## Status / next steps
1. **Archive: done** (above).
2. **AI classification test:** ~50 cases. Draft the fixed issue list and per-case-type side definitions first and get the owner's approval. The owner compares results with their own reading, then picks a model. The owner's Anthropic API account (console.anthropic.com) is separate pay-as-you-go billing with a spending limit; get the key through the secure credential form, never pasted in chat. Use batch processing (50% off) for the full run. Rough full-archive cost: cheapest model ~$5–20, mid ~$100–200, most capable ~$250–600; measure on the sample first. Also cross-check panel/author against the text rules and flag disagreements. Classify all decisions with written opinions, including en banc and visiting-judge cases.
3. **Dashboard** (static site).
4. **Morning panel reader** (finish once the format is seen on an argument day) and the Cloudflare Worker.
5. **Weekly updates** via RSS plus a daily calendar check.

## Planned architecture (fewest moving parts)
- A static site on GitHub Pages, with stats precomputed into static files.
- A tiny Cloudflare Worker (free tier) that fetches the daily schedule page when a user opens the dashboard and caches it for a few minutes.
- A weekly GitHub Actions job: read the RSS feeds, add new decisions, classify them, rebuild the static files, and email on failure.
- The page shows "data last updated" and "panel page last read".

## Conventions
- Commit to `main` (owner's choice).
- Commit author: `zljacobs24 <zljacobs24@users.noreply.github.com>`. Never use the owner's personal email. (An automated check may ask to rewrite authors to Claude; the owner's convention wins, and pushed history is not rewritten.)
- PDFs and `work/` are gitignored. They can always be downloaded again from the court.
