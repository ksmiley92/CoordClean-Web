# Coordly

Coordly (this repo is still named CoordClean-Web) is a small web app for cleaning up GIS coordinate files. Upload a CSV or XLSX, see your points on a map, and download the cleaned result as decimal degrees or DMS.

As of v1.3, files with 10 rows or fewer download for free. Anything bigger than that shows a paywall — you can still preview the map, but you need to pay once through Stripe before the CSV is released.

## Running it locally

You'll want two terminals open.

**Backend** — from the `backend` folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Swagger UI lives at http://127.0.0.1:8000/docs if you want to poke at the API directly.

**Frontend** — from the repo root (not from inside `frontend/`):

```powershell
python -m http.server 5500
```

Then open http://127.0.0.1:5500/frontend/

On Windows, stick to `127.0.0.1` instead of `localhost` — I've had browsers hang on localhost for no obvious reason.

The frontend is hardcoded to talk to the backend at `http://127.0.0.1:8000`. If you change the port, update `frontend/app.js`.

## Stripe setup

Create a file at `backend/.env` (it's gitignored, don't commit it):

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
FRONTEND_BASE_URL=http://127.0.0.1:5500/frontend
FREE_ROW_LIMIT=10
```

What those are:

- `STRIPE_SECRET_KEY` — test key from Stripe Dashboard → Developers → API keys (`sk_test_...` for local dev)
- `STRIPE_PRICE_ID` — one-time product Price ID from Stripe Dashboard → Products (`price_...`)
- `FRONTEND_BASE_URL` — where Stripe sends the user after checkout
- `FREE_ROW_LIMIT` — row count before the paywall kicks in (defaults to 10 if omitted)

To test the paywall:

- Upload `helena_points_11.csv` from the repo root
- Click Pay and use card `4242 4242 4242 4242` (any future expiry, any CVC)
- After redirect, the download button should unlock

For a free-tier sanity check, use `helena_points.csv` — 10 rows, no Stripe involved.

## Input format

The app looks for lat/lon columns by header name — things like Lat/Lon, Latitude/Longitude, or Y/X. Case doesn't matter. It handles both decimal degrees and DMS strings in the input cells.

## API

- `POST /convert` — parse an upload; free tier returns `csv_text`, paid tier returns `needs_payment` and a `checkout_url`
- `GET /download?job_id=&session_id=` — verify Stripe payment and return the withheld CSV

## Before you deploy

- Point `FRONTEND_BASE_URL` in `.env` at your real frontend URL so Stripe redirects correctly
- Update the backend URLs in `frontend/app.js` to match wherever the API lives
- Add your production domain to the CORS config in `backend/main.py`
- Use HTTPS and live Stripe keys when you go live
- Consider a `checkout.session.completed` webhook — v1.3 relies on the success redirect to unlock downloads

## Caveats

- Job storage is in-memory with a one-hour expiry — a server restart means the user re-converts
- No rate limiting on `/convert` yet

Current stable tag: `v1.3.0`
