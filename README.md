# LoseItForReal
Building my own system, tired of failing at weight loss. 

# Local-First Calorie Log (AI-Assisted)

This project is a **local-first calorie and meal logging system** designed to:

- remove calorie lookup anxiety
- preserve *what you actually ate* for reflection
- produce stable, trend-worthy calorie data
- work offline
- store everything in a Git repository
- require no accounts, databases, or cloud services

Calories are **estimated by AI** using consistent assumptions.  
You paste the result into a local app.  
You view progress via a static dashboard.

---

## Philosophy

There is rarely a single “correct” calorie number.

This system prioritizes:

- consistency over precision
- trends over exactness
- memory and reflection over databases
- durability over convenience features

If the estimates are stable, the trends are useful.

---

## How it works (high level)

1. You describe what you ate to an AI assistant (freeform text).
2. The AI returns a **Daily Log Block** (structured text).
3. You paste that block into a **local web app**.
4. The app:
   - validates the input
   - stores it as a JSON line
   - rebuilds dashboard data
5. You optionally `git commit` and `git push`.
6. You view progress via a static dashboard.

No logins.  
No API keys.  
No external services required.

---

## Repository layout

```

calorie-log/
├── data/
│   └── entries.jsonl        # Canonical log (one day per line)
├── tools/
│   ├── server.py            # Local paste-based logging app
│   └── parser.py            # Strict Daily Log Block parser
├── scripts/
│   └── build_site.py        # Builds dashboard data from JSONL
├── site/
│   ├── index.html           # Static dashboard
│   └── app.js               # Dashboard logic
├── .github/workflows/
│   └── build.yml            # Optional GitHub Action
└── README.md

````

---

## Quick start

### Requirements
- Python 3.x
- A web browser
- Git (optional but recommended)

No external Python libraries are required.

---

### Start the local logger

From the repo root:

```bash
python tools/server.py
````

Open in your browser:

```
http://127.0.0.1:8787
```

---

## Logging a day

### Step 1: Ask AI for an estimate

You describe your day naturally:

```
Eggs and toast for breakfast.
Chicken rice bowl for lunch.
Burger and fries out for dinner.
Protein bar later.
```

The AI returns a **Daily Log Block** like this.

---

### Step 2: Paste the Daily Log Block

Paste this **exact text** into the local app:

```
date: 2025-12-30
day_type: normal
source: ai_estimate

meals_text:
  breakfast: |
    eggs
    toast
    coffee with cream
  lunch: |
    chicken rice bowl
    broccoli
    sauce
  dinner: |
    burger
    fries
  snacks: |
    protein bar

estimates:
  breakfast_kcal: 350
  lunch_kcal: 650
  dinner_kcal: 1150
  snacks_kcal: 220
  total_kcal: 2370
  protein_g: 140

notes: |
  Dinner treated as restaurant food.
```

Click **Save**.

---

### What happens on save

* Entry is written to `data/entries.jsonl`
* Only one entry per date is allowed (overwrite optional)
* `site/data.json` is regenerated automatically
* Dashboard updates immediately

---

## Viewing progress

### Local dashboard

* Open `site/index.html`
* Or click “Open Dashboard” in the logger

### What you can see

* daily calories
* 7-day rolling average
* weekly averages
* click any day to see:

  * what you ate
  * notes
  * context (travel, social, etc.)

This answers:

* “Why did I go over?”
* “What worked?”
* “What meals are repeatable?”

---

## Data format (important)

### Canonical storage: JSON Lines

Each day is one line in `data/entries.jsonl`.

Example:

```json
{
  "date": "2025-12-30",
  "day_type": "normal",
  "source": "ai_estimate",
  "meals_text": {
    "breakfast": "eggs\ntoast\ncoffee with cream",
    "lunch": "chicken rice bowl\nbroccoli\nsauce",
    "dinner": "burger\nfries",
    "snacks": "protein bar"
  },
  "estimates": {
    "breakfast_kcal": 350,
    "lunch_kcal": 650,
    "dinner_kcal": 1150,
    "snacks_kcal": 220,
    "total_kcal": 2370,
    "protein_g": 140
  },
  "notes": "Dinner treated as restaurant food."
}
```

This file is:

* append-friendly
* git-friendly
* searchable
* future-proof

---

## Git workflow (optional)

You can use this system without git, but it shines with it.

Typical flow:

```bash
git status
git commit -am "Log 2025-12-30"
git push
```

If the GitHub Action is enabled:

* `site/data.json` is rebuilt automatically
* GitHub Pages can host the dashboard

---

## Why this system works

* You never debate calorie database entries
* You keep human memory, not just numbers
* AI absorbs uncertainty
* Trends remain stable
* Data is portable and durable
* No vendor lock-in

---

## Non-goals

This system intentionally does NOT:

* track individual food databases
* scan barcodes
* sync across devices automatically
* guarantee exact calorie accuracy

Those features add friction and anxiety.

---

## License

Use it, modify it, fork it.
This is a personal tool by design.

```

---

If you want, next we can:
- rename the project (and logo)
- tighten the README further
- add a one-page “Why this works” philosophy doc
- add a “failure modes” section for future-you

But yes — this README is **good enough for anyone to succeed**.
```
