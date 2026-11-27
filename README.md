# NeuroQuest — Brain Training Platform

A responsive browser-based brain-training game with username/password accounts, 60 challenge variations, daily tests and streaks, XP progression, a global leaderboard, achievements, personal analytics, sound effects, smooth animations, and an admin-only dashboard.

> NeuroQuest is a practice and entertainment game. It does not diagnose conditions or guarantee increases in intelligence or real-world cognitive performance.

## Features

- **Five training modes:** sequence memory, reaction timing, number logic, visual focus, and mental calculation.
- **60 challenge templates:** 12 named challenge levels for each of the five modes; tasks scale with level.
- **Daily Brain Test:** one five-skill test per local calendar day, shared daily sequence, and a +40 XP completion bonus.
- **Streaks:** consecutive active days and longest streak.
- **Accounts:** username + password; password hashes are stored, not plaintext passwords.
- **Progress:** XP, player level, completed sessions, best difficulty, and recent activity.
- **Global leaderboard:** ranked by XP with round count as a tie-breaker.
- **Achievements:** 12 unlockable milestones.
- **Analytics:** recent activity chart, average/best score, and per-mode statistics.
- **Admin dashboard:** site totals, active players, recent sessions, and top players; hidden and API-protected for non-admins.
- **Sound and animations:** browser-generated sound effects, animated UI, and reduced-motion support.

## Run locally

Python 3.11+ is recommended. Python 3.12 is used by the included Render Blueprint.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Deploy on Render

1. Push the project files to a GitHub repository.
2. In Render, choose **New + → Blueprint** and connect that repository.
3. Render reads `render.yaml` and provisions the web service and PostgreSQL database.
4. After the first deploy, open the web service's **Environment** settings and add:
   - `ADMIN_USERNAME` — the username for the administrator account.
   - `ADMIN_PASSWORD` — a unique password of at least 12 characters (use a long random password).
5. Save changes and redeploy. The app creates the admin account on startup if it does not already exist. If the username already exists, it is promoted to admin; its existing password is not overwritten.
6. Open the `onrender.com` URL, create a regular account, and sign in.

The Blueprint uses a free Render database plan as a starter configuration. Free database storage and lifetime are subject to Render's current plan limits; use a paid database and backups for lasting user progress.

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | Yes in production | Flask session signing key. Render Blueprint generates one. |
| `DATABASE_URL` | Yes in production | PostgreSQL connection string. Render Blueprint wires it automatically. |
| `ADMIN_USERNAME` | Optional | Creates/promotes the admin account at startup. |
| `ADMIN_PASSWORD` | Optional | Password for the admin account; set privately in Render, never commit it. |

## Security and deployment notes

- Never commit `.env`, database credentials, admin passwords, or session secrets.
- Passwords are hashed with Werkzeug before being stored.
- Session cookies are HttpOnly and SameSite=Lax; Secure cookies are enabled on Render.
- The admin API enforces server-side admin checks. Hiding the admin button is not the security boundary.
- Client-submitted game scores can be manipulated by a determined user. The leaderboard is suitable for a hobby project, not a cash-prize or competitive anti-cheat environment. Add server-validated game proofs and rate limits before operating a high-stakes competition.
- For real production usage, add database migrations, backups, rate limiting, monitoring, and an independent security review.

## Health check

`GET /health` returns a JSON status response for Render health checks.

## GitHub repository

This project is prepared for the private repository `black-hacker170/brantastgm` on the `main` branch. When cloning the repository, use:

```bash
git clone https://github.com/black-hacker170/brantastgm.git
```

After the source files are committed, connect `brantastgm` to Render with **New + → Blueprint**.
