# v1.29 Apple Music Metadata

## Objective

Add a read-only Apple Music surface for locally synced Music library track, playlist, and exact selected playlist-track metadata without returning audio bytes, lyrics, file paths, raw identifiers, play history, ratings, broad playlist track dumps, or mutating Music.app.

Apple documents Sync Library for Apple Music and iTunes Match as a way to make the user's music library available across signed-in devices. The local macOS Music library package is present on disk, but its `Library.musicdb` file is a proprietary binary format rather than SQLite. Public parser projects exist, including `rinsuki/musicdb2sqlite` and `pitetb/AppMusicLibParser`, but a first publishable tranche should avoid vendoring or reverse-engineering that binary format.

## Implemented Surface

- `local-apple-data music search --json --query <text>`
- `local-apple-data music get --json --handle <music:track:v1:...>`
- `local-apple-data music playlists --json --query <text>`
- `local-apple-data music playlist --json --handle <music:playlist:v1:...>`
- `local-apple-data music playlist-tracks --json --handle <music:playlist:v1:...>`
- MCP `music_search`
- MCP `music_get_track`
- MCP `music_search_playlists`
- MCP `music_get_playlist`
- MCP `music_list_playlist_tracks`

Track search returns bounded metadata for specific title, artist, album, album-artist, or genre queries. Playlist search returns bounded playlist name/type/count metadata for specific playlist-name queries. Selected playlist-track listing returns capped track metadata for one exact playlist handle.

Exact detail requires an opaque handle returned by the corresponding search flow.

## Returned Fields

- Opaque `music:track:v1:` or `music:playlist:v1:` handles.
- Track title, artist, album, album artist, genre, duration, track number, disc number, and year.
- Playlist title, kind, track count, and duration.
- Redaction booleans confirming raw identifiers, file paths, audio, lyrics, play history, ratings, and broad playlist track dumps are not returned.

## Non-Goals

- Broad Music library dumps.
- Audio/video export or inline media bytes.
- Lyrics export or broad lyrics search.
- Local file paths, raw Music persistent IDs, raw database IDs, or direct `.musicdb` parsing.
- Play history, skip counts, ratings, favorites/loved state, cloud-account state, recommendations, listening queue, or playback position.
- Broad playlist track dumps, playlist creation/update/delete, library import/delete, playback/queue control, Music.app mutation, iCloud media fetch, or Apple Music network/API access.

## Implementation Notes

- The first tranche uses bounded Music.app AppleScript automation through `osascript` because the local `Library.musicdb` format is proprietary and not SQLite.
- Health checks only for `osascript`, Music.app presence, and the default Music library package; health does not open Music.app or inspect tracks.
- Runtime verification uses a synthetic runner. It does not read the operator's real Music library.
- Future performance work can add a separate native parser design if it can be proven with synthetic fixtures, stable redaction, no raw path/identifier leakage, and no durable personal-content cache.

## Tests

- Synthetic adapter tests cover search, exact track get, exact playlist get, exact selected playlist-track listing, invalid handles, broad-query rejection, automation errors, and raw identifier/path/audio/lyrics redaction.
- CLI tests cover all five Music commands.
- MCP tests cover invalid-handle failure and tool registration.
- Runtime smoke covers opaque Music handles and redaction guarantees through a mocked runner.
- Surface-contract audit covers CLI, MCP, health, access requirements, and this matrix.
