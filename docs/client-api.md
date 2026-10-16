# The client API

Everything a FieldStation42 client needs from the server, over plain HTTP on the server's port
(4242 by default). There is no login: anyone who can reach the server can use it. The Python
client in `client/` uses exactly these endpoints; another client (an Android TV app, say) can be
built on them alone.

Times are the server's local time, ISO 8601 without an offset (`2026-10-16T20:00:00`). A client
plays against the server's clock: keep `offset = server_time - local time when the response
arrived` and use `local now + offset` as "now".

## `GET /client/version`

```json
{"version": "2101ce3235aaf9dabd968636b9c6781ca736862f", "server_time": "2026-10-16T16:10:15.565824"}
```

`version` changes whenever a schedule is built or reset, or a station config or a file in
`/client/files` changes. Poll it (the Python client does every 10 s) and fetch the rundown and
files again when it changes.

## `GET /client/rundown?hours=24`

Every block of every scheduled station that is on now or starts within `hours`, plus metadata
for the files they play.

```json
{
  "version": "…",
  "server_time": "2026-10-16T16:10:15",
  "stations": {
    "DevTV": [
      {
        "liquid_type": "LiquidBlock",
        "start_time": "2026-10-16T16:10:00",
        "end_time": "2026-10-16T16:15:00",
        "title": "Show1",
        "break_strategy": "standard",
        "break_info": {"bump_dir": "bumps", "commercial_dir": "commercials", "...": "..."},
        "sequence_key": null,
        "content": {"path": "catalog/devtv/shows/show1.mp4", "title": "show1", "tag": "shows",
                    "duration": 240.0, "content_type": "feature", "media_type": "video"},
        "plan": [
          {"path": "catalog/devtv/shows/show1.mp4", "skip": 0, "duration": 120.0,
           "is_stream": false, "content_type": "feature", "media_type": "video"},
          {"path": "catalog/devtv/bumps/bump2.mp4", "skip": 0, "duration": 5.0,
           "is_stream": false, "content_type": "bump", "media_type": "video"}
        ]
      }
    ]
  },
  "meta": {"catalog/devtv/shows/show1.mp4": {"type": "episode", "title": "Pilot", "show_title": "DevTV"}}
}
```

- `content` is one object, a list (clip shows), or `null`.
- `liquid_type` is `LiquidBlock`, `LiquidClipBlock`, `LiquidLoopBlock`, `LiquidOffAirBlock` or
  `LiquidWebBlock`.
- Streaming, guide and web stations have no blocks: they are played from their station config.

**What plays at time `t`:** take the block with `start_time <= t <= end_time` (the earlier one
wins at an exact boundary). Walk its `plan` adding up `duration` from `start_time`; the entry
whose span contains `t` plays, starting `skip + (t - entry start)` seconds into its file. If the
plan ends before the block does, play the station's `be_right_back_media` for the rest, or
nothing. `shared/rundown.py` (`play_point`) is the reference implementation.

**Plan entry paths** are one of:
- a server path such as `catalog/devtv/shows/show1.mp4` or `runtime/signoff.mp4`: fetch it from
  `/client/media`;
- a URL (`is_stream: true`, or anything containing `://`): play it directly;
- `:autobump:=<url>`: a web page to render for `duration` seconds instead of a video. The URL
  points at `http://127.0.0.1:4242/static/bump/bump.html?...`; the Python client answers that
  address itself and proxies it to the server. Another client should replace
  `http://127.0.0.1:4242` with the server's address.

## `GET /client/media?path=<plan path>`

The file's bytes, with HTTP Range support, so a player can open a file at any offset. Allowed
paths are files the catalog scanned, files under a station's `content_dir` or `runtime/`, and a
station's standby, BRB, sign-off and off-air media. Anything else is `403`; a missing file is
`404`. URL-encode the path (`quote(path, safe="")`).

## `GET /client/files` and `GET /client/file?path=`

The small files a client reads from disk, and one of them by path:

```json
[{"path": "confs/devtv.json", "size": 912, "mtime": 1792157400.1},
 {"path": "runtime/standby.png", "size": 51234, "mtime": 1792150000.0}]
```

The list holds every station config (`confs/*.json`, including `main_config.json`), station
standby and off-air images, logo folders, and the guide channel's images and music. The Python
client mirrors them into the same relative paths, removes station configs the server no longer
lists, and merges its own `main_config` overrides from `client.json` over the server's
`main_config.json`.

## Everything else

The web console's data routes (`/schedules`, `/summary`, `/ppv`, `/media`, `/static`, ...) are
also open; the web pages a client shows (guide, PPV, bumps, the remote) call them.
