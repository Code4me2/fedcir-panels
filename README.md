# fedcir-panels

Dashboard for Federal Circuit argument days: shows the panel assigned to each case (posted about an hour before argument) and historical statistics for those judges, including how often they sit together, how each judge has voted on the issue in a case, and time from argument to decision.

## Data sources (all public, from www.cafc.uscourts.gov)
- **Sitemap** (`sitemap_index.xml`): index of every opinion, Rule 36 judgment and oral-argument recording posting. It is used to locate opinion PDFs and argued cases.
- **Opinion PDFs**: panel, author, separate opinions, decision date, origin and precedential status are extracted with text rules (no AI).
- **RSS feeds**: new opinions and recordings for ongoing updates.
- **Calendar PDFs and daily schedule page**: upcoming cases and argument-morning panels.

Coverage starts in 2015, the first year the court's sitemap is complete.

## Layout
- `scripts/`: data collection and extraction
- `data/`: sitemap index and extracted data
- `samples/`: test runs used to check extraction quality
