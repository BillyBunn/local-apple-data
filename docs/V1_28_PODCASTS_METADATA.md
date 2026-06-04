# v1.28 Apple Podcasts Metadata

## Goal

Add a read-only Apple Podcasts surface for locally synced Podcasts show metadata, bounded episode lists, and selected-episode descriptions without returning transcripts, audio bytes, feed/enclosure URLs, local download paths, raw identifiers, opening Podcasts.app, fetching iCloud-only media, or mutating the library.

## Approved Surface

- CLI: `local-apple-data podcasts search`
- CLI: `local-apple-data podcasts get`
- CLI: `local-apple-data podcasts episodes`
- CLI: `local-apple-data podcasts episode`
- MCP: `podcasts_search`
- MCP: `podcasts_get_show`
- MCP: `podcasts_list_episodes`
- MCP: `podcasts_get_episode`

Search reads local Apple Podcasts metadata from `MTLibrary.sqlite` and returns bounded show title, author, category, provider, subscription/hidden status, episode counts, recent timestamps, and opaque `podcasts:show:v1:` handles.

Exact show get returns the same selected-show metadata by opaque handle.

Episode listing returns bounded episode metadata for one selected show handle, including title, author, duration, publish/playback metadata, saved/downloaded state, media kind, and transcript availability status. It does not return episode descriptions, transcript identifiers, audio URLs, local download paths, or raw identifiers.

Exact episode detail returns bounded selected-episode description text only by opaque `podcasts:episode:v1:` handle.

## Privacy Boundary

Allowed:

- Specific show title, author, category, or provider searches.
- Exact selected-show metadata by `podcasts:show:v1:` handle.
- Bounded selected-show episode metadata by exact show handle.
- Bounded selected-episode description text by exact `podcasts:episode:v1:` handle.
- Schema-only health checks for `ZMTPODCAST` and `ZMTEPISODE`.

Blocked:

- Broad Podcasts library dumps.
- Broad episode-description search or dumps.
- Transcript text, transcript identifiers, or transcript export.
- Audio/video bytes, audio export, enclosure URLs, feed URLs, web URLs, local download paths, or media-cache paths.
- Raw show UUIDs, episode UUIDs, GUIDs, store IDs, track IDs, account IDs, or database rows.
- iCloud-only media fetches or network access.
- Opening Podcasts.app to force sync.
- Chapter metadata, playback queue, station, subscription management, listening history beyond bounded selected-show metadata, or recommendations as first-tranche surfaces.
- Any Apple Podcasts mutation.

## Verification

- Synthetic adapter tests cover schema checks, search, exact show get, selected-show episode listing, exact episode detail, invalid handles, broad-query rejection, truncation, and raw identifier/path/URL/transcript redaction.
- CLI tests cover `podcasts search`, `podcasts get`, `podcasts episodes`, and `podcasts episode`.
- MCP list tests include `podcasts_search`, `podcasts_get_show`, `podcasts_list_episodes`, and `podcasts_get_episode` as read-only tools.
- Runtime smoke builds a synthetic Podcasts SQLite store and verifies opaque handles, metadata-only search/listing, exact bounded episode description retrieval, invalid-handle rejection, and no raw identifier leakage.
- Surface-contract, release-readiness, public-release, and redaction scans must pass before publication.
