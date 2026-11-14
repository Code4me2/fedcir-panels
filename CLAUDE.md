# Project notes: fedcir-panels

The owner is a patent attorney, new to software projects. They want a critical thinking partner: answer in chat (no separate documents unless asked), give a recommendation instead of a survey, explain technical steps in plain language, and keep moving parts to a minimum because nobody technical will maintain this.

## Goal
A free, public web dashboard for Federal Circuit argument days. The court posts each panel about one hour before argument (daily schedule is posted by 9:00 a.m.). For each case the dashboard shows:
- how often the panel's judges have sat together, as pairs and as the trio;
- for the issue the user picks from a dropdown, how each judge has voted, by side, compared with the court-wide rate, with sample sizes;
- authorship share and time from argument to decision.

## Decisions made (don't revisit without the owner)
- **Coverage starts in 2015.** The court's sitemap is ~complete from 2015 (2015: 516 vs 514 in the court's table; 2016: 543 vs 547). 2013 (~10%) and 2014 (~77%) are incomplete. Pre-2015 could be added later from CourtListener.
- **All case types are included**, not only patent cases. "Side" is defined per case type: patent owner vs challenger/accused infringer; veteran, employee, contractor or importer vs government.
- **Every judge's vote counts**, unanimous or not. Dissents are recorded as votes on the other side. There is no separate dissent section.
- **Votes are shown by the side they favored, in the issue's own terms** (e.g. "voted ineligible"), plus disposition (affirmed/reversed/vacated). "Appellant won" is not used on its own.
- **Court-wide baseline** is shown next to each judge's rate.
- **Rule 36 judgments are left out of outcome statistics (option a)** and tracked separately, e.g. as a Rule 36 rate. They are used for sit-together counts (their PDFs list the panel). Outcome labels say "in cases with written decisions".
- **The user picks the issue from a dropdown** on the dashboard. Pulling issues automatically from appeal filings is a possible future feature.
- **Panel, author, date, separate opinions, origin and precedential status come from free text rules, not AI.** AI is used only for issues and outcomes.
- **Fixed, fine-grained issue list** (merging later is free, splitting needs a re-run). Store the label, a one-sentence description and a supporting quote for each issue so later changes rarely need a re-run.
- **Claim construction is coded by its effect on the judgment**, e.g. a vacated noninfringement judgment favors the patentee. Use "other/unclear" when the effect isn't clear; those count in n but not in percentages.
- **Argument dates:** recordings posted on bulk-upload days (more than 100 in a day: 2013-07-30, 2014-11-12, 2015-07-20, 2015-08-06, 2015-10-30) count as argued but have no date. They are excluded from time-to-decision.

## Data sources (www.cafc.uscourts.gov, allowed in the cloud environment)
- **Do not bypass the court's bot-check.** The Opinions & Orders and recordings tables load from a wpDataTables admin-ajax feed behind an Azure WAF JavaScript challenge. Reading it with a headless browser was blocked as circumventing access protection. Don't do it.
- **Sitemap** (`/sitemap_index.xml`, referenced by robots.txt, which allows everything): lists every opinion, Rule 36 judgment and "audio-uploaded" posting. Saved in `data/sitemap/all_post_urls.txt`. PDF addresses can be predicted from posting slugs (new format `{appeal}.OPINION.{m-d-yyyy}_{id}.pdf`, old format `{appeal}.opinion.{m-d-yyyy}.{n}.pdf`); otherwise the posting page links the PDF. 1,198 postings dated 2025-03-10 are a re-posting of old decisions and are skipped.
- **PDFs** are not bot-checked. Download politely: about 1.5 s between requests, honest User-Agent.
- **RSS feeds** for ongoing updates: `/category/opinion-order/feed/` (latest ~100 postings, about 3 weeks) and `/category/oral-argument/feed/` (about 2 months). Poll weekly.
- **Calendar:** `/home/oral-argument/scheduled-cases/` links monthly PDFs (`PublicCalendar-<Month><Year>.pdf`) listing panel letter, date, courtroom, appeal number, origin, case name and [argued]/[on the briefs]. These PDFs get revised, so re-check daily before a session.
- **Panels:** `/home/oral-argument/daily-schedule/` is plain HTML, not bot-checked. The panel-name format hasn't been seen yet; first chance is the December 2026 session (starts Mon Dec 7).

## Planned architecture (fewest moving parts)
- A static site on GitHub Pages, with stats precomputed into static files.
- A tiny Cloudflare Worker (free tier) that fetches the daily schedule page when a user opens the dashboard and caches it for a few minutes.
- A weekly GitHub Actions job: read the RSS feeds, add new decisions, classify them, rebuild the static files, and email on failure.
- The page shows "data last updated" and "panel page last read".

## Status / next steps
1. **Archive (in progress):** `scripts/build_archive.py` downloads ~8,094 decisions from 2015 on (6,063 opinions + 2,031 Rule 36) and writes `data/decisions.csv` plus extracted text in `data/text/text_<year>.jsonl.gz`. It is resumable and checkpoints to GitHub every 500. After it finishes: review the flags (panel, author, date, origin, author/dissenter not on panel), add rules for new patterns, re-extract from the saved text (`--extract-only`, no re-download), and check for rare judge names (possible misreads).
2. **AI classification test:** ~50 cases. The owner compares results with their own reading, then picks a model. The owner's Anthropic API account is separate pay-as-you-go billing with a spending limit. Use batch processing for the full run. Rough full-archive cost: cheapest model ~$5–20, mid ~$100–200, most capable ~$250–600; measure on the sample first. Also cross-check panel/author against the text rules and flag disagreements.
3. **Dashboard** (static site).
4. **Morning panel reader** (finish once the format is seen on an argument day) and the Cloudflare Worker.
5. **Weekly updates** via RSS plus a daily calendar check.

## Conventions
- Commit to `main` (owner's choice).
- Commit author: `zljacobs24 <zljacobs24@users.noreply.github.com>`. Never use the owner's personal email.
- PDFs and `work/` are gitignored. They can always be downloaded again from the court.
