from io import BytesIO
import re

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

MAX_FILE_SIZE = 5 * 1024 * 1024

# Accepted header aliases (case-insensitive). Order = priority if multiple match.
LAT_NAMES = ["lat", "latitude", "y"]
LON_NAMES = ["lon", "long", "lng", "longitude", "x"]
LABEL_NAMES = ["name", "label", "id"]

app = FastAPI(title="CoordClean", version="1.0")

# Allow the frontend to call us whether it's opened as file://, served via
# `python -m http.server`, or running on any other localhost port.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    output_format: str = Form(...),
):
    output_format = output_format.lower()
    if output_format not in {"dd", "dms"}:
        raise HTTPException(status_code=400, detail="output_format must be 'dd' or 'dms'.")

    # Read the whole upload into memory once; small enough given MAX_FILE_SIZE.
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
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
            raise HTTPException(status_code=400, detail="Unsupported file type. Use .csv or .xlsx.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")

    # Map lowercased headers -> original column names so we can match aliases
    # case-insensitively while still indexing the DataFrame by its real column.
    column_map = {str(c).strip().lower(): c for c in df.columns}
    lat_col = next((column_map[k] for k in LAT_NAMES if k in column_map), None)
    lon_col = next((column_map[k] for k in LON_NAMES if k in column_map), None)
    label_col = next((column_map[k] for k in LABEL_NAMES if k in column_map), None)

    if lat_col is None or lon_col is None:
        raise HTTPException(
            status_code=400,
            detail="Could not detect latitude/longitude columns. Expected headers like Lat/Lon, Latitude/Longitude, or Y/X.",
        )

    # Coerce to numeric (non-numeric -> NaN) and drop rows outside valid ranges.
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")

    valid = df[lat_col].between(-90, 90) & df[lon_col].between(-180, 180)
    df = df[valid].reset_index(drop=True)

    if df.empty:
        raise HTTPException(
            status_code=400,
            detail="No valid coordinate rows found (lat must be -90..90, lon must be -180..180).",
        )

    # Signed decimal -> "DD°MM'SS.SS"H", e.g. 46.5854172 -> 46°35'07.50"N.
    def to_dms(value: float, is_lat: bool) -> str:
        hemisphere = ("N" if value >= 0 else "S") if is_lat else ("E" if value >= 0 else "W")
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

    csv_text = out_df.to_csv(index=False)

    stem = re.sub(r"\.(csv|xlsx)$", "", filename, flags=re.IGNORECASE) or "coordclean"
    download_name = f"{stem}_{output_format}.csv"

    return {
        "points": points,
        "csv_text": csv_text,
        "filename": download_name,
        "row_count": len(out_df),
    }
