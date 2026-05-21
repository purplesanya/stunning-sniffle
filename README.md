# FLoader

A small Flask web app for searching authors/books and downloading selected books.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe app.py
```

The app starts on `http://127.0.0.1:5000` by default.

Optional environment variables:

- `PORT`: override the local port.
- `FLASK_RUN_HOST`: override the host. Keep `127.0.0.1` for local-only use.
- `FLASK_DEBUG=1`: enable Flask debug mode during development.
- `LOG_LEVEL`: set Python logging level, for example `DEBUG` or `INFO`.

To test from another device or LAN address, run with `FLASK_RUN_HOST=0.0.0.0` and open the machine IP, for example `http://HOST_IP:5000`.

## Deploy on Render

This repo includes `render.yaml`, `Procfile`, and `.python-version` for Render.

Dashboard setup:

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
- Health Check Path: `/healthz`

Blueprint setup:

1. Push this project to GitHub/GitLab/Bitbucket.
2. In Render, choose **New > Blueprint**.
3. Select the repo and let Render read `render.yaml`.

Notes for Render:

- The filesystem is ephemeral, which is fine here because downloads are temporary and bookmarks live in the browser.
- Free instances can sleep, so the first request after inactivity may be slow.
- Flibusta availability depends on Render's outbound network access from the selected region.

## Notes

Use this only for books you are legally allowed to download. The app validates download links before fetching them, keeps temporary outputs behind per-job tokens, and expires in-memory jobs after one hour.

Supported download formats found on Flibusta pages: `fb2`, `epub`, `mobi`, `pdf`, and `docx`. A single selected book is returned as the original file. Two or more selected books are bundled into a ZIP archive.

The web UI also includes community recommendations parsed from `/rec`, direct download links for recommendation cards, lazy-loaded book descriptions, author biographies, local browser bookmarks, Russian/English UI text with browser-language detection, and keyboard-layout tolerant search for mistyped Russian queries.
