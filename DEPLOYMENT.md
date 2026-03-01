# BlindSight AI — Deployment Guide

---

## Before you start — API keys you need

| Key | Where to get it |
|-----|----------------|
| OpenAI API Key | https://platform.openai.com/api-keys |
| Stream API Key | https://dashboard.getstream.io (free tier works) |
| Stream API Secret | Same dashboard, project settings |

---

## Part 1 — Deploy the Python Agent to Heroku

The Python agent is a long-running **worker** dyno that joins a Stream call and
runs the AI vision loop. It does not serve HTTP.

### Step 1 — Install the Heroku CLI

```bash
curl https://cli-assets.heroku.com/install.sh | sh
heroku login
```

### Step 2 — Create and configure the Heroku app

```bash
cd blindsight-backend

# Create the app (you can replace blindsight-ai-agent with any unique name)
heroku create blindsight-ai-agent

# Set all environment variables
heroku config:set OPENAI_API_KEY=sk-...your_key...
heroku config:set STREAM_API_KEY=your_stream_api_key
heroku config:set STREAM_API_SECRET=your_stream_api_secret

# Confirm they are set
heroku config
```

### Step 3 — Deploy

```bash
# Make sure you are in blindsight-backend/
git init
git add .
git commit -m "Initial deploy"
heroku git:remote -a blindsight-ai-agent
git push heroku main
```

### Step 4 — Scale the worker dyno

Heroku does NOT start worker dynos by default after deploy.

```bash
# Turn off the default web dyno (there is none, but just in case)
heroku ps:scale web=0

# Start the worker
heroku ps:scale worker=1

# Confirm it is running
heroku ps
```

Expected output:
```
=== worker (Standard-1X): python main.py --call-type default --call-id blindsight-live (1)
worker.1: up 2026/03/01 00:00:00 +0000 (~ 10s ago)
```

### Step 5 — Check live logs

```bash
heroku logs --tail -a blindsight-ai-agent
```

You should see the agent connect to Stream and wait for calls.

### Notes
- The worker uses a Standard-1X dyno ($7/month). Free tier eco dynos sleep — not suitable for a long-running agent.
- The `Procfile` already contains the correct command: `worker: python main.py --call-type default --call-id blindsight-live`
- `requirements.txt` was generated from the uv lockfile and is pinned for reproducible deploys.
- `runtime.txt` pins Python 3.12.3.

---

## Part 2 — Deploy the Next.js Frontend to Vercel

### Option A — Vercel CLI (fastest, under 2 minutes)

```bash
cd blindsight-frontend
npm install -g vercel

# Deploy to production
vercel --prod
```

During the first deploy Vercel will ask:
- Set up and deploy? **Y**
- Which scope? Select your account
- Link to existing project? **N**
- Project name: **blindsight-frontend** (or any name)
- In which directory is your code located? **./**
- Want to modify settings? **N**

After the deploy completes you get a URL like `https://blindsight-frontend.vercel.app`.

### Step 2 — Set environment variables on Vercel

```bash
vercel env add NEXT_PUBLIC_STREAM_API_KEY
# Paste your Stream API key, select all environments (Production, Preview, Development)

vercel env add STREAM_API_SECRET
# Paste your Stream API secret, select all environments

# Redeploy to pick up the env vars
vercel --prod
```

Or set them in the Vercel dashboard: Project > Settings > Environment Variables.

### Option B — GitHub auto-deploy

1. Push `blindsight-frontend/` to a GitHub repo
2. Go to https://vercel.com/new, import the repo
3. Add the two env vars in the Vercel UI
4. Click Deploy

Every `git push` to main will auto-deploy.

---

## Part 3 — Run locally (development)

### Backend

```bash
cd blindsight-backend
cp .env.example .env        # fill in your keys
source .venv/bin/activate
python main.py --call-type default --call-id blindsight-live
```

### Frontend

```bash
cd blindsight-frontend
cp .env.local.example .env.local   # fill in your keys
npm run dev
# Open http://localhost:3000
```

---

## Architecture overview

```
iPhone Safari
    |
    | WebRTC (Stream edge)
    |
Next.js frontend (Vercel)    <-->  /api/token  (JWT)
    |
    | Stream Video call: default/blindsight-live
    |
Python Agent (Heroku worker)
    |
    | GPT-4o Realtime API (OpenAI)
    |
    Speech back to user via Stream audio track
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Heroku worker crashes on start | Run `heroku logs --tail` — usually a missing env var |
| Camera does not start on iPhone | Must be HTTPS. Vercel provides HTTPS automatically. |
| "userId required" error | The `/api/token` route was called without a `userId` param |
| Agent not responding | Check that `--call-id blindsight-live` matches `CALL_ID` in `page.tsx` |
| Peer dep warnings on npm install | Expected — `.npmrc` adds `legacy-peer-deps=true` automatically |
