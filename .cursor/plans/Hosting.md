---
name: Hostinger Render Deploy
overview: "Two-phase production deploy: Phase 1 puts the FastAPI backend on Render (test keys, API verification). Phase 2 uploads the static frontend to Hostinger after you buy the domain, wires URLs/CORS/Stripe, and runs end-to-end live tests."
todos:
  - id: code-cors-env
    content: Add CORS_ORIGIN env var to backend/main.py (keep localhost regex for dev)
    status: completed
  - id: code-env-example
    content: Create/update backend/.env.example with production vars
    status: completed
  - id: phase1-render
    content: "Phase 1: Deploy backend to Render Web Service, set test Stripe env vars, verify /convert via Swagger"
    status: pending
  - id: phase2-domain
    content: "Phase 2a: Buy domain and attach to Hostinger (user handles DNS)"
    status: pending
  - id: phase2-wire
    content: "Phase 2b-c: Update Render FRONTEND_BASE_URL + CORS_ORIGIN, update app.js Render URLs, upload frontend to Hostinger"
    status: pending
  - id: phase2-e2e
    content: "Phase 2d: Full E2E test matrix (free, paywall, pay, download, cancel)"
    status: pending
  - id: readme-deploy
    content: Add Deploy section to README referencing this plan
    status: completed
isProject: false
---

# Coordly — Hostinger + Render Deploy Plan

## How this plan works

Do things in order. Don't skip ahead.

**Phase 1** — Get the backend running on Render and test it with Swagger. No domain needed yet.

**Phase 2** — Buy your domain, upload the frontend to Hostinger, point everything at each other, test the full app.

**Before Phase 1** — Make a few small code changes in the repo so production URLs come from env vars instead of hardcoded localhost.

---

## Overview

- **Frontend** (static HTML/JS/CSS) → Hostinger → `https://YOUR_DOMAIN/`
- **Backend** (FastAPI) → Render → `https://coordly-api.onrender.com` (or whatever name Render gives you)

Hostinger domain/DNS setup is **out of scope** — you handle that in Phase 2 when you buy the domain.

---

## Step 0 — Code changes (before Phase 1)

Do these in the repo first, then push to GitHub so Render can pull them.

### 0a. CORS for production — [backend/main.py](backend/main.py)

Today CORS only allows localhost. Add a `CORS_ORIGIN` env var (e.g. `https://YOUR_DOMAIN`) and pass it to `allow_origins` while keeping the existing localhost regex for local dev.

### 0b. Env template — create `backend/.env.example`

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
FRONTEND_BASE_URL=https://YOUR_DOMAIN
CORS_ORIGIN=https://YOUR_DOMAIN
FREE_ROW_LIMIT=10
```

### 0c. README — add a short Deploy section

Note Render free-tier cold starts and in-memory job limits.

**Don't change `frontend/app.js` yet** — that happens in Phase 2 when you know your Render URL and domain.

---

## Phase 1 — Backend on Render

**Goal:** A live API at `https://<something>.onrender.com`. Test with Swagger. Buy the domain later.

### Step 1 — Push code to GitHub

Render deploys from GitHub. Make sure your branch (e.g. `v1-Backend`) has the Step 0 changes pushed.

### Step 2 — Create a Render account and connect GitHub

1. Go to [render.com](https://render.com) and sign up (or log in).
2. From the Render Dashboard, click **Account Settings** (or **Integrations**) and connect your **GitHub** account.
3. Grant Render access to the **CoordClean-Web** repo when prompted.

### Step 3 — Create a new Web Service

1. On the Render Dashboard, click **New +** → **Web Service**.
2. Find **CoordClean-Web** in the repo list and click **Connect**.
3. Fill in the settings:

**Basic**
- **Name:** `coordly-api` (or whatever you like — this becomes part of your URL)
- **Region:** pick one close to your users (e.g. Ohio / Oregon)
- **Branch:** `v1-Backend` (or your release branch)
- **Root Directory:** `backend` ← important; the API lives in the `backend/` folder, not repo root
- **Runtime:** Python 3

**Build & Deploy**
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

Do **not** use `--reload` on Render.

**Instance type**
- **Free** is fine for now (accept cold starts — first request after idle can take ~30 seconds)

4. **Don't click Deploy yet** — set env vars first (Step 4).

### Step 4 — Add environment variables

Still on the service setup page (or later: your service → **Environment** in the left sidebar):

Click **Add Environment Variable** for each of these:

- `STRIPE_SECRET_KEY` = your Stripe **test** secret key (`sk_test_...`)
- `STRIPE_PRICE_ID` = your Stripe **test** Price ID (`price_...`)
- `FRONTEND_BASE_URL` = `https://YOUR_DOMAIN` (placeholder is fine for now — you'll update it in Phase 2)
- `FREE_ROW_LIMIT` = `10`
- `CORS_ORIGIN` = leave empty or use the same placeholder — not needed until Phase 2

**Where to get Stripe test keys:** Stripe Dashboard → toggle **Test mode** (top right) → Developers → API keys. Create a one-time product in Test mode for the Price ID.

### Step 5 — Deploy

1. Click **Create Web Service** (or **Save Changes** then **Manual Deploy → Deploy latest commit** if editing an existing service).
2. Watch the **Logs** tab. You should see:
   - Build: `pip install -r requirements.txt` completing
   - Deploy: `Uvicorn running on http://0.0.0.0:10000` (or similar)
   - Status badge turns **Live** (green)
3. Copy your service URL from the top of the page — e.g. `https://coordly-api.onrender.com`. **Save this**; you'll need it in Phase 2 for `app.js`.

### Step 6 — Test the API (no domain required)

Open `https://<your-service>.onrender.com/docs` in a browser.

**First load may be slow** on the free tier — Render wakes the service from sleep. Wait up to ~30 seconds.

Run these tests in Swagger:

1. **POST /convert** with `helena_points.csv` (10 rows)
   - Expect: `csv_text` in the response, no paywall
2. **POST /convert** with `helena_points_11.csv` (11 rows)
   - Expect: `needs_payment: true`, a `job_id`, and a `checkout_url` starting with `cs_test_...`

You can skip the full paywall redirect test for now — that needs your real frontend URL (Phase 2).

### Step 7 — Troubleshooting Render

**Build failed**
- Check Logs for a missing dependency — compare with [backend/requirements.txt](backend/requirements.txt)
- Confirm **Root Directory** is `backend`

**Service won't start**
- Confirm **Start Command** is exactly: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Check Logs for Python import errors

**502 / service unavailable**
- Free tier may still be waking up — wait and retry
- Check Logs for crash loops

**Paid convert returns 503**
- `STRIPE_SECRET_KEY` or `STRIPE_PRICE_ID` missing or wrong in Environment

### Phase 1 done when

- [ ] Render service status is **Live**
- [ ] `/docs` loads
- [ ] 10-row convert returns `csv_text`
- [ ] 11-row convert returns `checkout_url`
- [ ] You saved your Render URL (e.g. `https://coordly-api.onrender.com`)

---

## Phase 2 — Frontend on Hostinger + go live

**Goal:** App on your domain, talking to Render, Stripe redirects working.

### Step 1 — Buy domain and attach to Hostinger

You handle DNS / pointing the domain at Hostinger. Ensure the site loads over **HTTPS**.

Pick one canonical URL and use it everywhere — e.g. `https://coordly.app` **or** `https://www.coordly.app`, not both.

### Step 2 — Update Render environment variables

Go to Render Dashboard → your service → **Environment**:

- `FRONTEND_BASE_URL` → `https://YOUR_DOMAIN` (exact URL users will visit)
- `CORS_ORIGIN` → same origin (must match what the browser sends — `www` vs non-`www` matters)
- When ready for real payments: swap to **live** `STRIPE_SECRET_KEY` and live `STRIPE_PRICE_ID`

Click **Save Changes**. Render will redeploy automatically.

### Step 3 — Update frontend for production

Edit [frontend/app.js](frontend/app.js) — replace localhost with your Render URL:

```javascript
const backendUrl = "https://coordly-api.onrender.com/convert";
const backendDownloadUrl = "https://coordly-api.onrender.com/download";
```

Use your actual Render service URL from Phase 1.

### Step 4 — Upload to Hostinger

Upload these three files to your Hostinger **document root** (`public_html`):

- `index.html`
- `app.js`
- `style.css`

All three must be in the **same folder**. Users should hit `https://YOUR_DOMAIN/` and see the app.

### Step 5 — End-to-end tests

- **10-row file** (`helena_points.csv`) — convert + download, no paywall
- **11-row file** (`helena_points_11.csv`) — map shows, paywall appears, no `csv_text` in browser Network tab
- **Pay** — test card `4242 4242 4242 4242` (test keys) or real card (live keys)
- **After redirect** — URL has `?session_id=...&job_id=...`, status says "Payment received", Download works
- **Cancel on Stripe** — returns with `?cancelled=1`, download still blocked

If convert fails with a CORS error in DevTools, `CORS_ORIGIN` on Render doesn't match your frontend URL exactly.

### Step 6 — Tag release

When everything works: `git tag v1.3.0`

### Phase 2 done when

- [ ] `https://YOUR_DOMAIN/` loads the app
- [ ] Free tier convert + download works
- [ ] Paid tier: pay → redirect → download works
- [ ] Live Stripe keys in place (if going live for real customers)

---

## Later (not blocking launch)

- Stripe **webhook** (`checkout.session.completed`) — unlocks download even if user closes tab after paying
- Render **paid tier** — avoids cold starts and sleep-related job loss
- Persistent job store (Redis) — survives Render restarts
- Custom API subdomain (`api.YOUR_DOMAIN`) — optional; Render default URL is fine for v1
