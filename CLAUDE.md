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
- **Issue statistics are matched to forum** (confirmed by the owner 2026-11-15). Forum (from the origin field) is stored with each issue, and the dashboard by default shows a judge's record on the chosen issue in the same forum as the case being argued (the calendar lists the origin), e.g. obviousness in PTAB appeals vs district-court appeals vs ex parte appeals.
- **Pro se flag** (confirmed 2026-11-15): a text rule (not AI) reads the counsel listing and flags pro se parties, so the dashboard can filter them out; pro se jurisdictional dismissals would otherwise dominate veterans, employment and Court of Federal Claims records.
- **Vacated/remanded issues favor the side that appealed on the issue actually decided** (confirmed 2026-11-15). Only issues the court decides are coded; if the court vacates for inadequate agency explanation without reaching the merits, only the explanation issue is coded.
- **Small samples** (confirmed 2026-11-15): issues are stored at full detail; the dashboard decides at build time whether a narrow issue is shown by itself, merged into its group, or as a court-wide rate only.

## Methodology: issue list and coding rules (step 2, approved by the owner 2026-11-15)
**Source of truth:** `data/issue_list.csv` (70 codes in 12 groups: patent validity; claim scope and infringement; patent defenses and remedies; PTAB trial procedure; ITC; trademark; veterans; federal employment; government contracts; other Court of Federal Claims; trade; procedure for any case type, incl. X99 "Other") and `data/sides.csv` (Side A / Side B for 12 case types). Each code has a label for each side and a one-sentence "covers" description that goes into the AI instructions. The workbook the owner reviewed is kept as `review/issue_list_reviewed_2026-11-15.xlsx` (approved without edits). Groups are the levels the dashboard can merge into when samples are small. If more than ~5% of issues in the test land in X99, a code is missing.

**Sides.** Private-vs-private: patent owner vs accused infringer / petitioner / requester; trademark applicant/registrant/owner vs opposer/petitioner/PTO/accused infringer. Government cases: the private party (veteran, employee, contractor/protester, claimant, importer) vs the government. Antidumping/countervailing duty cases use **lower vs higher duties**, not parties, because Commerce may have ruled either way. Interferences have no side. *Clarified 2026-11-15:* inter partes reexams (a third-party requester is a party) go with PTAB trials; only ex parte reexams go with ex parte appeals (applicant vs PTO).

**Coding rules (all confirmed by the owner).** For each written decision the AI records the case type and, for each issue the court actually decided: the code, the side favored (or *mixed*, or *other/unclear*), the disposition, the judges dissenting on that issue, a one-sentence description and a supporting quote.
- Only decided issues are coded; issues the court "need not reach" are not.
- Vacated/remanded favors the side that appealed, on the issue decided (e.g. vacated for inadequate explanation = X06 only).
- Dissents are per issue: a partial dissent counts on the other side only for the issues it covers. Concurrences count with the majority.
- Forfeiture is its own issue (X04), coded for the side that benefits, not as a ruling on the underlying issue.
- *Mixed* (some claims each way) is a separate outcome, shown as its own share on the dashboard. *Other/unclear* counts in n, not in percentages.
- Claim construction is coded by its effect on the judgment (above).

**Test sample** (`samples/classification_test_50.csv`, made by `scripts/select_test_sample.py`, seed 20261115). 35 patent cases (13 PTAB trial or inter partes reexam, 5 ex parte appeal/reexam, 14 district court, 3 ITC) and 15 others (2 TTAB, 3 veterans, 3 federal employment, 3 Court of Federal Claims, 1 Board of Contract Appeals, 2 CIT, 1 district-court non-patent). Drawn at random within each group, except 7 patent slots reserved for opinions with a dissent and 1 for an en banc decision, and patent groups balanced to about half precedential (24 of 50 overall). Left out of the draw: no-panel, superseded and 2-judge-panel decisions, and interferences. The groups come from rough text rules used only for this draw (PTO: "inter partes review/post-grant/CBM", IPR/PGR/CBM numbers, "inter partes reexamination" or a 95/ control number = two-party; district court: "patent" 5+ times = patent, never = non-patent, in between left out); the AI records the case type itself. Dissents and precedential opinions are over-represented, so the test's cost per case is scaled to the whole archive by text length, not multiplied out directly.

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
- *Origin:* from the caption line "Appeal from …", "Petition for review of …" (MSPB, arbitrators) or "Petition for Writ of Mandamus to …": TTAB 171, PTO (PTAB/BPAI/examiner) 2,178, ITC 87, district court 1,960, Court of Federal Claims 1,065, MSPB 1,097, Veterans Court 946, CIT 279, Boards of Contract Appeals 132, arbitrator 57. Direct petitions against an agency use the respondent: VA 23, DOJ 14, Office of Congressional Workplace Rights 13, GAO 1. With no caption line (8 decisions, e.g. a PDF whose first page has no caption), the first page is scanned, with "District Court" checked last because visiting district judges' footnotes name one. *Fixed 2026-11-15:* the rule first read only "… from …", so 79 decisions (mostly MSPB petitions, which say "of") had been labeled from a scan of the first page, often wrongly as district court.
- *Appeal numbers:* from the slug, normalized to YY-NNNN, including consolidated numbers.
- *Argued / time to decision:* a decision is matched to "audio-uploaded" recording postings by appeal number; the argument date is the latest recording date on or before the decision date. **Assumption:** a recording's posting date is its argument date (recordings are normally posted the same day); bulk-upload days give "yes (date unknown)". Results: 5,279 with an argument date, 359 argued with unknown date, 2,385 not argued (submitted on the briefs). For opinions with dates (n = 3,442): median 69 days from argument to decision, 90th percentile 190, max 805.

**Flags** (column `flag`; 1–3% of decisions):
- 65 "panel not found": the PDF has no panel (mostly unsigned pro se per curiam opinions, and a January 2019 batch of Rule 36 judgments whose panel is only a signature image). 63 "author" are mostly the same decisions. Excluded from judge stats rather than adding another source.
- 23 "en banc"; 6 "2-judge panel" (genuine: a judge died or recused); 4 "superseded by revised opinion"; 5 "appeal number" (2009-style or miscellaneous-docket numbers like 2015-145); 1 "decided before 2015" (a 2015 re-issue of a 2014 opinion, kept).
- 76 appeals have 2+ opinions (Supreme Court remands, en banc rehearings, second appeals). These are real separate rulings and count separately, except revised re-issues (above).

**Re-running.** `python3 scripts/build_archive.py --extract-only` re-applies the rules to the saved text with no downloads (rebuilds `work/text/` from `data/text/` in a fresh session; tested to reproduce the CSV exactly). Without `--extract-only` it downloads anything missing (resumable). `--no-push` skips the GitHub commit. Background jobs are capped at 2 hours; ask the owner before relaunching a job that hit the cap.

**Test samples** (in `samples/`): 40 recent decisions from RSS, and 98 decisions stratified 7 per year 2013–2026 (seed 20261114), used to develop the rules before the full run.

## Status / next steps
1. **Archive: done** (above).
2. **AI classification test:** issue list, sides and coding rules approved; 50 test cases selected (both 2026-11-15, above). Next: write the classifier, run it on the 50. The owner compares results with their own reading, then picks a model. The owner's Anthropic API account (console.anthropic.com) is separate pay-as-you-go billing with a spending limit; get the key through the secure credential form, never pasted in chat. Use batch processing (50% off) for the full run. Rough full-archive cost: cheapest model ~$5–20, mid ~$100–200, most capable ~$250–600; measure on the sample first. Also cross-check panel/author against the text rules and flag disagreements. Classify all decisions with written opinions, including en banc and visiting-judge cases.
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
