# Improvement Plan

## Product and UX

- Keep the webapp as the only supported client.
- Add a real reading list flow: bookmarks, recently viewed books, and export/import of saved items.
- Add clear empty, loading, and error states for every network-dependent page.
- Keep mobile as a first-class layout: sticky filters, large tap targets, and no horizontal overflow.

## Search and Discovery

- Expand keyboard-layout tolerant search and add typo-tolerant matching for common Russian names.
- Add recommendations from Flibusta community pages and cache them server-side.
- Enrich recommendations and search results with lazy-loaded book descriptions and direct download formats.
- Add filters for author pages: format, title, and maybe series/language if the source page exposes them.
- Add optional “search inside bookmarked books” on the bookmarks page.

## Downloads

- Keep single selected books as direct files and use ZIP only for two or more files.
- Validate all proxied links against allowed Flibusta download paths before fetching.
- Add clearer per-book download errors in bulk jobs instead of only a final job error.
- Consider a setting for preferred default format.

## Backend Quality

- Move cache/job state into small service classes once the app grows past a single file.
- Add unit tests for parsers using saved HTML fixtures.
- Add integration tests for download job states and invalid link rejection.
- Add request timeouts, retry limits, and small rate limits for every Flibusta call.

## Frontend Quality

- Keep HTML, CSS, and JS separated.
- Avoid inline event handlers and use data attributes for behavior.
- Add automated visual smoke tests for desktop and mobile breakpoints.
- Add accessible keyboard behavior for selection, bookmarks, language switch, and filters.
- Keep the recommendation page as a single mobile-first feed instead of dense competing columns.

## Deployment

- Add a production run path with Waitress or Gunicorn depending on OS.
- Add config for host, port, log level, cache TTL, and max bulk download count.
- Keep temporary download files short-lived and never expose raw temp paths.

## Legal and Safety

- Keep the app framed around books the user is allowed to download.
- Avoid storing account credentials or cookies.
- Keep bookmarks local unless an explicit sync feature is added later.
