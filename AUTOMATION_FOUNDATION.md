# Bounded ZEUS Scraper Jobs

This branch imports the original ZEUS Python Flask scraper and adds an **opt-in**, synchronous one-chapter route.

## New route
`POST /automation/scrape-chapter` — requires the unchanged existing scraper `API_SECRET` as `Authorization` header. Body: `{sourceUrl,chapterNumber,adminEmail}`.

The route:
1. Resolves an approved source plugin and confirms the actual hostname matches.
2. Fetches metadata and chapter catalog.
3. Checks whether the chapter was already stored.
4. Scrapes one chapter, writes it through C-flow's existing `/api/scraper/receive`, then acknowledges completion.

No new server process, queue loop, or daemon thread is launched by this route. Old `/scrape`, `/sites`, `/health` and scheduler endpoints are untouched.

## Deploying
Use a **preview**, never replace the current production scraper automatically. Configure `NODE_BACKEND_URL` to target a suitable C-flow backend and preserve `API_SECRET`.

See `tests/test_automation.py` and GitHub Actions. Some source plugins do not implement the generic catalog adapter and require separate support. Check terms/licences before scraping.

## Updated durable storage contract
The automation endpoint requires the matching C-floww backend revision with
`/api/automation/chapters/check` and `/api/automation/chapters/import`.
Set NODE_BACKEND_URL to isolated staging and provision its named Firestore database.
Legacy endpoints remain available, but automation never falls back to their old
acknowledgement semantics. See ENGINEERING_AUDIT_AR.md for tested scope and blockers.
