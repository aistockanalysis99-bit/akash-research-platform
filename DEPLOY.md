# Deploying Akash Research Platform

**Architecture:** React frontend on **Vercel** → FastAPI backend on **Render**.
The backend holds the database, runs the scheduler, and calls FMP / Unusual
Whales / Gemini / Claude / Telegram.

> ⚠️ **Render must be a paid plan (Starter, ~$7/mo).** The scheduler needs an
> always-on instance, and the persistent disk (SQLite + dossiers) is paid-only.
> The free tier sleeps when idle and has no persistent storage.

---

## 1. Push to GitHub

```bash
git init
git add .
git commit -m "Akash Research Platform"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

`.env`, `runs.sqlite`, caches and build output are gitignored — **no secrets
or runtime data get pushed.** Verify with `git status` before committing.

## 2. Backend → Render

1. **New + → Blueprint**, pick the repo. Render reads `render.yaml` and
   provisions the `akash-backend` web service + a 5 GB disk at `/var/data`.
2. In the service's **Environment** tab, set the secret values (these are
   `sync:false` in the blueprint, so they're entered by hand):
   `FMP_API_KEY`, `UW_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`,
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
3. Deploy. Health check is `GET /health`. Note the URL,
   e.g. `https://akash-backend.onrender.com`.

Storage (DB + dossiers + cache) lives on the mounted disk via the
`DB_PATH=/var/data/...` env vars — it survives restarts and redeploys.

## 3. Frontend → Vercel

1. **New Project**, pick the same repo.
2. Set **Root Directory = `frontend`** (Vercel auto-detects Vite via
   `frontend/vercel.json`).
3. Add env var **`VITE_API_BASE`** = your Render backend URL
   (e.g. `https://akash-backend.onrender.com`, no trailing slash).
4. Deploy. The app loads from Vercel and calls the Render backend.

## 4. Verify

- Backend: `https://<render-url>/health` → `{"status":"ok"}`
- Frontend: open the Vercel URL → Portfolio loads with live data.

---

## Notes

- **CORS** is currently `*` (works out of the box). To lock it down later,
  restrict `allow_origins` in `api/main.py` to your Vercel domain.
- **Durability:** Render's disk is persistent but single-instance. For extra
  safety, add **Litestream** to replicate `runs.sqlite` to Cloudflare R2 / S3.
- **Scaling to Postgres:** when you add more clients, migrate SQLite → managed
  Postgres (Neon/Supabase); the schema is small and clean.
- **Local dev** is unchanged: `cd frontend && npm run dev` + `python run.py --no-browser`.
