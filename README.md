```markdown
# LoseItForReal (Local Calorie Log)

A tiny, local-first calorie logging app.

- Stores your daily entries in a single file: `data/entries.jsonl`
- Simple dashboard: trends, 7-day rolling average, filters, day detail
- Edit-in-place log editor: load a date, edit, save (merge or overwrite)
- Dark / Light / System theme toggle (saved in your browser)

No accounts. No cloud. No database. Just files in your repo.

---

## Folder Structure

```

LoseItForReal/
├── data/
│   └── entries.jsonl
│
├── site/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   ├── log.html
│   └── log.js
│
└── tools/
└── server.py

````

---

## Requirements

- Python 3 (recommended: 3.10+)

That’s it.

---

## Run It

From the repo root:

```bash
python tools/server.py
````

Then open:

* Dashboard: `http://127.0.0.1:8787/`
* Add/Edit entry: `http://127.0.0.1:8787/log`

Optional: change port

```bash
python tools/server.py 9999
```

---

## Data File Format (JSONL)

Your data lives here:

* `data/entries.jsonl`

JSONL = “JSON Lines” = one JSON object per line.

Example line:

```json
{"date":"2025-12-30","day_type":"normal","source":"ai_estimate","meals_text":{"breakfast":"...","lunch":"...","dinner":"...","snacks":"..."},"estimates":{"breakfast_kcal":250,"lunch_kcal":600,"dinner_kcal":900,"snacks_kcal":300,"total_kcal":2050},"notes":"optional","updated_at":"2025-12-30T22:15:00Z"}
```

---

## Editing an Entry

Go to `/log`.

### Load

* Pick a date and click **Load**
* Or click **Today**

### Save behavior

You have two choices when the date already exists:

1. **Merge/Append**

* Appends text in `meals_text` fields instead of replacing them
* Overwrites `estimates` keys you provide
* Safer for adding snacks later without blowing away earlier meals

2. **Overwrite**

* Replaces the entire entry for that date with what is in the editor

If both are checked, Merge wins (safer).

### Save & Go to Dashboard

Saves and returns to `/`.

---

## Theme Toggle (System / Dark / Light)

Both pages have a theme button:

* Theme: System
* Theme: Dark
* Theme: Light

The setting is stored in your browser using `localStorage` key:

* `loseit_theme`

This is local to your browser profile.

---

## API Endpoints (Local Only)

The UI uses two JSON endpoints:

### Load entry

`GET /api/entry?date=YYYY-MM-DD`

Returns:

* existing entry for that date, or
* a default template if none exists

### Save entry

`POST /api/save`

Body:

```json
{
  "entry": { "...": "..." },
  "merge": true,
  "overwrite": false
}
```

Returns:

```json
{ "ok": true, "message": "Saved...", "date": "YYYY-MM-DD" }
```

---

## Common Issues

### Dashboard says it can’t load entries.jsonl

Make sure you started the server:

```bash
python tools/server.py
```

Then refresh the page.

### I edited entries.jsonl manually and it broke

If a line is not valid JSON, the dashboard will treat it as corrupt and ignore it.

Fix the bad line or delete it.

---

## Backup / Sync

This app is designed for Git repos.

Recommended workflow:

* Commit `data/entries.jsonl` as you go
* Push to your private repo for backup

---

## License


