"""
ETL_joshua.py

Fetches speaker counts per language from the Joshua Project API,
saves raw + processed CSVs, and loads into PostgreSQL.

Source:  Joshua Project People Groups API
Table:   joshua_project_speakers
Columns: iso639_3 (PK, FK → glottolog_languages), language_name, speaker_count
"""

import time
import pandas as pd
import requests
from pathlib import Path
from urllib.parse import quote_plus
from sqlalchemy import (
    create_engine, MetaData, Table, Column,
    String, Text, Integer, ForeignKey, text
)

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT  = Path.cwd().parents[1]
RAW_DIR       = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
ISO_SOURCE    = PROCESSED_DIR / "glottolog_languages.csv"

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY   = "78447f1289af"       # ← paste your Joshua Project API key
BASE_URL  = "https://api.joshuaproject.net/v1/people_groups.json"
PAGE_SIZE = 100
DELAY     = 0.3                       # seconds between requests

DB_PASSWORD = quote_plus("Ed5205")   # ← paste your DB password
DB_URL = (
    f"postgresql+psycopg2://postgres:{DB_PASSWORD}"
    f"@localhost:5433/langauge_vitality_database"
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Saved {len(df)} rows → {path}")


# ── Extract ───────────────────────────────────────────────────────────────────
def load_iso_codes(path: Path) -> list[str]:
    """Load valid ISO 639-3 codes from the Glottolog processed CSV."""
    df = pd.read_csv(path, usecols=["iso639_3"], dtype=str)
    codes = df["iso639_3"].dropna().str.strip()
    codes = codes[codes.str.match(r"^[a-z]{3}$")]
    return sorted(codes.unique().tolist())


def fetch_people_groups(api_key: str) -> pd.DataFrame:
    """Page through the Joshua Project people_groups endpoint and return raw DataFrame."""
    records = []
    page = 1

    print("Fetching people groups from Joshua Project API...")
    while True:
        params = {
            "api_key": api_key,
            "limit":   PAGE_SIZE,
            "page":    page,
            "fields":  "ROL3,PrimaryLanguageName,PopulationPGAC",
        }
        resp = requests.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            break

        records.extend(data)
        print(f"  Page {page}: {len(data)} records (total so far: {len(records)})")

        if len(data) < PAGE_SIZE:
            break

        page += 1
        time.sleep(DELAY)

    print(f"Fetched {len(records)} people group records total")
    return pd.DataFrame(records)


# ── Transform ─────────────────────────────────────────────────────────────────
def aggregate_speakers(pg_df: pd.DataFrame, iso_codes: list[str]) -> pd.DataFrame:
    """Sum population per ISO 639-3 code, filter to Glottolog ISO codes."""
    pg_df = pg_df.copy()
    pg_df["ROL3"]       = pg_df["ROL3"].astype(str).str.strip().str.lower()
    pg_df["PopulationPGAC"] = pd.to_numeric(pg_df["PopulationPGAC"], errors="coerce").fillna(0)

    iso_set = set(iso_codes)
    pg_df   = pg_df[pg_df["ROL3"].isin(iso_set)]

    name_df = (
        pg_df.groupby("ROL3")["PrimaryLanguageName"]
        .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0])
        .reset_index()
        .rename(columns={"ROL3": "iso639_3", "PrimaryLanguageName": "language_name"})
    )

    pop_df = (
        pg_df.groupby("ROL3")["PopulationPGAC"]
        .sum()
        .reset_index()
        .rename(columns={"ROL3": "iso639_3", "PopulationPGAC": "speaker_count"})
    )

    result = (
        name_df
        .merge(pop_df, on="iso639_3")
        .sort_values("iso639_3")
        .reset_index(drop=True)
    )
    result["speaker_count"] = result["speaker_count"].astype(int)
    return result


# ── Load ──────────────────────────────────────────────────────────────────────
def load_to_postgres(df: pd.DataFrame, engine) -> None:
    """Truncate and reload joshua_project_speakers table."""
    metadata = MetaData()

    with engine.connect() as conn:
        metadata.reflect(bind=conn)

    Table(
        "joshua_project_speakers",
        metadata,
        Column("iso639_3",      String(3), ForeignKey("glottolog_languages.iso639_3"), primary_key=True),
        Column("language_name", Text),
        Column("speaker_count", Integer),
        extend_existing=True,
    )

    with engine.begin() as conn:
        metadata.create_all(conn)
        conn.execute(text("TRUNCATE TABLE joshua_project_speakers CASCADE"))
        print("Table ready (truncated if existed)")

    df.to_sql(
        "joshua_project_speakers",
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )
    print(f"Loaded {len(df)} rows into joshua_project_speakers")
    engine.dispose()

# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    # 1. Load ISO reference codes
    iso_codes = load_iso_codes(ISO_SOURCE)
    print(f"Loaded {len(iso_codes)} ISO codes from Glottolog\n")

    # 2. Fetch raw people groups
    raw_df = fetch_people_groups(API_KEY)
    save_dataframe(raw_df, RAW_DIR / "joshua_project_people_groups_raw.csv")

    # 3. Aggregate to one row per language
    speakers_df = aggregate_speakers(raw_df, iso_codes)
    coverage = len(speakers_df) / len(iso_codes) * 100
    print(f"\nCoverage: {len(speakers_df)} / {len(iso_codes)} ISO codes matched ({coverage:.1f}%)")
    print(speakers_df.head(10).to_string(index=False))

    # 4. Save processed CSV
    save_dataframe(speakers_df, PROCESSED_DIR / "joshua_project_speakers.csv")

    # 5. Load into PostgreSQL
    print("\nLoading into PostgreSQL...")
    engine = create_engine(DB_URL)
    try:
        load_to_postgres(speakers_df, engine)
    finally:
        engine.dispose()
        print("Engine disposed")

    print("\nPipeline complete!")
    

if __name__ == "__main__":
    main()
