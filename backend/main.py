from io import BytesIO
import os
import re
import time
from uuid import uuid4

import pandas as pd
import stripe
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

max_file_size = 5 * 1024 * 1024
free_row_limit = int(os.getenv("FREE_ROW_LIMIT", "10"))
job_ttl_seconds = 3600
frontend_base_url = os.getenv(
    "FRONTEND_BASE_URL", "http://127.0.0.1:5500/frontend").rstrip("/")
cors_origin = os.getenv("CORS_ORIGIN", "").strip()
stripe_price_id = os.getenv("STRIPE_PRICE_ID")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Paid conversions: csv_text is held here until GET /download verifies Stripe payment.
jobs = {}


def cleanup_expired_jobs() -> None:
    """Remove paid-tier jobs older than job_ttl_seconds from the in-memory store."""
    now = time.time()
    expired = [
        job_id
        for job_id, job in jobs.items()
        if now - job["created_at"] > job_ttl_seconds
    ]
    for job_id in expired:
        del jobs[job_id]


def store_job(csv_text: str, filename: str) -> str:
    """Save a paid conversion's CSV and return a new job_id for checkout and download."""
    cleanup_expired_jobs()
    job_id = str(uuid4())
    jobs[job_id] = {
        "csv_text": csv_text,
        "filename": filename,
        "created_at": time.time(),
    }
    return job_id


def get_job(job_id: str):
    """Return the stored job dict, or None if the job_id is unknown or expired."""
    cleanup_expired_jobs()
    return jobs.get(job_id)


def create_checkout_url(job_id: str) -> str:
    """Start a Stripe Checkout Session for this job and return the hosted payment URL."""
    if not stripe.api_key or not stripe_price_id:
        raise HTTPException(
            status_code=503,
            detail="Payment is not configured. Set STRIPE_SECRET_KEY and STRIPE_PRICE_ID in backend/.env.",
        )
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": stripe_price_id, "quantity": 1}],
            metadata={"job_id": job_id},
            success_url=f"{frontend_base_url}/?session_id={{CHECKOUT_SESSION_ID}}&job_id={job_id}",
            cancel_url=f"{frontend_base_url}/?cancelled=1",
        )
    except stripe.StripeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not start checkout: {exc.user_message or str(exc)}")
    if not session.url:
        raise HTTPException(
            status_code=502, detail="Stripe did not return a checkout URL.")
    return session.url


# Accepted header aliases (case-insensitive). Order = priority if multiple match.
lat_names = ["lat", "latitude", "y"]
lon_names = ["lon", "long", "lng", "longitude", "x"]
label_names = ["name", "label", "id"]

# DMS parser (Standard tier): canonical "46°35'07.50\"N", integer seconds,
# DDM "46°35.125'N", signed-without-hemisphere "-112°01'06.45\"".
# Curly quotes and the masculine ordinal are normalized to canonical chars first.
dms_pattern = re.compile(
    r"""
    ^\s*
    (-?)\s*                           # optional sign
    (\d+(?:\.\d+)?)\s*°\s*            # degrees
    (?:(\d+(?:\.\d+)?)\s*'\s*)?       # optional minutes
    (?:(\d+(?:\.\d+)?)\s*"\s*)?       # optional seconds
    ([NSEWnsew]?)                     # optional hemisphere
    \s*$
    """,
    re.VERBOSE,
)


def parse_coordinate(value, is_lat: bool) -> float:
    """Parse one coordinate cell as decimal degrees or a DMS string."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return float("nan")

    # Normalize the Unicode quirks Excel / Google Maps copy-paste tends to introduce.
    s = value.strip()
    s = s.replace("\u2019", "'").replace("\u2032", "'")
    s = s.replace("\u201D", '"').replace("\u2033", '"')
    s = s.replace("\u00BA", "\u00B0")

    # Plain numeric strings ("46.5854") short-circuit before the regex.
    try:
        return float(s)
    except ValueError:
        pass

    m = dms_pattern.match(s)
    if not m:
        return float("nan")

    sign_str, deg_str, min_str, sec_str, hemi = m.groups()
    try:
        deg = float(deg_str)
        minutes = float(min_str) if min_str else 0.0
        seconds = float(sec_str) if sec_str else 0.0
    except ValueError:
        return float("nan")

    if minutes >= 60 or seconds >= 60:
        return float("nan")

    # Reject hemisphere letters that contradict the axis (e.g. "N" in a lon column).
    hemi = hemi.upper()
    if hemi:
        if is_lat and hemi not in ("N", "S"):
            return float("nan")
        if not is_lat and hemi not in ("E", "W"):
            return float("nan")

    magnitude = abs(deg) + minutes / 60.0 + seconds / 3600.0
    if hemi in ("S", "W"):
        return -magnitude
    if hemi in ("N", "E"):
        return magnitude
    # No hemisphere → the sign on the degrees (or explicit leading "-") is authoritative.
    if sign_str == "-" or deg < 0:
        return -magnitude
    return magnitude


app = FastAPI(title="CoordClean", version="1.3")

# Local dev: localhost regex. Production: set CORS_ORIGIN to your frontend URL (e.g. https://coordly.app).
cors_middleware_kwargs = {
    "allow_origin_regex": r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if cors_origin:
    cors_middleware_kwargs["allow_origins"] = [cors_origin]

app.add_middleware(CORSMiddleware, **cors_middleware_kwargs)


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    output_format: str = Form(...),
):
    """Parse a CSV/XLSX upload, return map points, and either csv_text (free) or a Stripe checkout URL (paid)."""
    output_format = output_format.lower()
    if output_format not in {"dd", "dms"}:
        raise HTTPException(
            status_code=400, detail="output_format must be 'dd' or 'dms'.")

    # Read the whole upload into memory once; small enough given max_file_size.
    contents = await file.read()
    if len(contents) > max_file_size:
        raise HTTPException(status_code=400, detail="File exceeds 5 MB limit.")

    # Parse based on extension. Wrap in try/except so pandas errors become 400s.
    filename = file.filename or "upload"
    lower_name = filename.lower()
    try:
        if lower_name.endswith(".csv"):
            df = pd.read_csv(BytesIO(contents))
        elif lower_name.endswith(".xlsx"):
            df = pd.read_excel(BytesIO(contents), engine="openpyxl")
        else:
            raise HTTPException(
                status_code=400, detail="Unsupported file type. Use .csv or .xlsx.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not parse file: {exc}")

    # Map lowercased headers -> original column names so we can match aliases
    # case-insensitively while still indexing the DataFrame by its real column.
    column_map = {str(c).strip().lower(): c for c in df.columns}
    lat_col = next((column_map[k] for k in lat_names if k in column_map), None)
    lon_col = next((column_map[k] for k in lon_names if k in column_map), None)
    label_col = next((column_map[k]
                     for k in label_names if k in column_map), None)

    if lat_col is None or lon_col is None:
        raise HTTPException(
            status_code=400,
            detail="Could not detect latitude/longitude columns. Expected headers like Lat/Lon, Latitude/Longitude, or Y/X.",
        )

    # Parse each cell as DD or DMS; unparseable cells become NaN and are dropped below.
    df[lat_col] = df[lat_col].apply(lambda v: parse_coordinate(v, is_lat=True))
    df[lon_col] = df[lon_col].apply(
        lambda v: parse_coordinate(v, is_lat=False))

    valid = df[lat_col].between(-90, 90) & df[lon_col].between(-180, 180)
    original_count = len(df)
    df = df[valid].reset_index(drop=True)
    dropped_count = original_count - len(df)

    if df.empty:
        raise HTTPException(
            status_code=400,
            detail="No valid coordinate rows found (lat must be -90..90, lon must be -180..180).",
        )

    # Signed decimal -> "DD°MM'SS.SS"H", e.g. 46.5854172 -> 46°35'07.50"N.
    def to_dms(value: float, is_lat: bool) -> str:
        hemisphere = ("N" if value >= 0 else "S") if is_lat else (
            "E" if value >= 0 else "W")
        absolute = abs(value)
        degrees = int(absolute)
        minutes_full = (absolute - degrees) * 60
        minutes = int(minutes_full)
        seconds = (minutes_full - minutes) * 60
        return f"{degrees}\u00B0{minutes:02d}'{seconds:05.2f}\"{hemisphere}"

    # Points are always DD because Leaflet needs numeric lat/lon for markers.
    points = []
    for _, row in df.iterrows():
        point = {"lat": float(row[lat_col]), "lon": float(row[lon_col])}
        if label_col is not None and pd.notna(row[label_col]):
            point["label"] = str(row[label_col])
        points.append(point)

    # Downloadable CSV: same schema as the input, with lat/lon reformatted if requested.
    out_df = df.copy()
    if output_format == "dms":
        out_df[lat_col] = [to_dms(v, True) for v in df[lat_col]]
        out_df[lon_col] = [to_dms(v, False) for v in df[lon_col]]

    # Leading BOM (U+FEFF) makes Excel-on-Windows open the file as UTF-8 instead of
    # Windows-1252, which would otherwise render "°" as "Â°".
    csv_text = "\ufeff" + out_df.to_csv(index=False)

    stem = re.sub(r"\.(csv|xlsx)$", "", filename,
                  flags=re.IGNORECASE) or "coordclean"
    download_name = f"{stem}_{output_format}.csv"
    row_count = len(out_df)

    if row_count > free_row_limit:
        job_id = store_job(csv_text, download_name)
        checkout_url = create_checkout_url(job_id)
        return {
            "points": points,
            "row_count": row_count,
            "dropped_count": dropped_count,
            "needs_payment": True,
            "job_id": job_id,
            "checkout_url": checkout_url,
        }

    return {
        "points": points,
        "csv_text": csv_text,
        "filename": download_name,
        "row_count": row_count,
        "dropped_count": dropped_count,
    }


@app.get("/download")
async def download(
    job_id: str = Query(...),
    session_id: str = Query(...),
):
    """Verify Stripe payment for a job_id, then return the withheld csv_text and filename."""
    if not stripe.api_key:
        raise HTTPException(
            status_code=503,
            detail="Payment is not configured. Set STRIPE_SECRET_KEY in backend/.env.",
        )

    job = get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404, detail="Conversion job not found or expired.")

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.StripeError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid payment session: {exc.user_message or str(exc)}")

    if session.payment_status != "paid":
        raise HTTPException(status_code=402, detail="Payment not completed.")

    metadata_job_id = session.metadata["job_id"] if session.metadata else None
    if metadata_job_id != job_id:
        raise HTTPException(
            status_code=403, detail="Payment session does not match this conversion.")

    return {"csv_text": job["csv_text"], "filename": job["filename"]}
