"""
Extract language vitality data from Wikidata via SPARQL.

Reads ISO 639-3 codes from the Glottolog CSV and queries Wikidata
in batches for vitality-related properties. Outputs a standalone
table keyed by iso639_3 for loading into PostgreSQL as a separate
table joined via foreign key.

Fetched properties:
  - Ethnologue/EGIDS language status (P3823)
  - Writing system (P282)
  - Language family (P279)
  - Wikidata QID

Requirements:
    pip install requests pandas
"""

from pathlib import Path
from urllib.parse import quote_plus
import re
import time

import pandas as pd
import requests
from sqlalchemy import (
    create_engine,
    text,
    Table,
    Column,
    MetaData,
    String,
    ForeignKey,
)

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
BATCH_SIZE = 200
RETRY_DELAY = 5
MAX_RETRIES = 3

password = quote_plus("Ed5205")
DB_URL = f"postgresql+psycopg2://postgres:{password}@localhost:5433/langauge_vitality_database"

SPARQL_TEMPLATE = """
SELECT ?iso ?wd ?wdLabel
       ?egids ?egidsLabel ?writingSystem ?writingSystemLabel ?familyLabel
WHERE {{
  VALUES ?iso {{ {iso_values} }}

  ?wd wdt:P220 ?iso .

  # Filter: entity must be an instance/subclass of "language" (Q34770)
  ?wd wdt:P31/wdt:P279* wd:Q34770 .

  OPTIONAL {{ ?wd wdt:P3823 ?egids . }}
  OPTIONAL {{ ?wd wdt:P282 ?writingSystem . }}
  OPTIONAL {{ ?wd wdt:P279 ?family . }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""

ISO_PATTERN = re.compile(r"^[a-z]{3}$")


def build_iso_values(codes: list[str]) -> str:
    """Format ISO codes for SPARQL VALUES clause."""
    return " ".join(f'"{c}"' for c in codes)


def query_wikidata(sparql: str) -> list[dict]:
    """Execute SPARQL query with retries."""
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "LanguageVitalityProject/1.0 (research)",
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                SPARQL_ENDPOINT,
                params={"query": sparql},
                headers=headers,
                timeout=120,
            )
            if resp.status_code in (429, 500):
                wait = RETRY_DELAY * (attempt + 2)
                print(f"  HTTP {resp.status_code}, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["results"]["bindings"]
        except requests.exceptions.Timeout:
            print(f"  Timeout on attempt {attempt + 1}, retrying...")
            time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(RETRY_DELAY)
    return []


def get_val(row: dict, key: str) -> str:
    """Extract value from SPARQL result binding."""
    return row.get(key, {}).get("value", "")


def extract_qid(uri: str) -> str:
    """Extract QID from Wikidata URI."""
    if uri and "/" in uri:
        return uri.rsplit("/", 1)[-1]
    return uri


def is_resolved_label(value: str) -> bool:
    """Check if a label was resolved (not a raw URI)."""
    return bool(value) and not value.startswith("http")


def extract_wikidata_languages(iso_codes: list[str]) -> pd.DataFrame:
    """Batch-query Wikidata and return a DataFrame keyed by iso639_3."""
    enrichment: dict[str, dict] = {}
    total_batches = (len(iso_codes) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(iso_codes), BATCH_SIZE):
        batch = iso_codes[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} codes)...")

        sparql = SPARQL_TEMPLATE.format(iso_values=build_iso_values(batch))
        results = query_wikidata(sparql)

        for r in results:
            iso = get_val(r, "iso")
            if not iso or not ISO_PATTERN.match(iso):
                continue

            if iso not in enrichment:
                enrichment[iso] = {
                    "iso639_3": iso,
                    "wd_qid": "",
                    "wd_label": "",
                    "egids_status": "",
                    "writing_systems": set(),
                    "language_family": "",
                }

            e = enrichment[iso]

            qid = extract_qid(get_val(r, "wd"))
            if qid:
                e["wd_qid"] = qid

            label = get_val(r, "wdLabel")
            if label:
                e["wd_label"] = label

            egids = get_val(r, "egidsLabel")
            if is_resolved_label(egids):
                e["egids_status"] = egids

            ws = get_val(r, "writingSystemLabel")
            if is_resolved_label(ws):
                e["writing_systems"].add(ws)

            family = get_val(r, "familyLabel")
            if is_resolved_label(family):
                e["language_family"] = family

        time.sleep(2)

    for e in enrichment.values():
        ws = e.get("writing_systems", set())
        e["writing_systems"] = "; ".join(sorted(ws)) if ws else ""

    return pd.DataFrame(enrichment.values())


def save_dataframe(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8")


def load_to_postgres(df: pd.DataFrame, db_url: str) -> None:
    engine = create_engine(db_url)
    metadata = MetaData()

    metadata.reflect(bind=engine, only=["glottolog_languages"])

    wikidata_languages = Table(
        "wikidata_languages",
        metadata,
        Column("iso639_3", String(3), ForeignKey("glottolog_languages.iso639_3"), primary_key=True),
        Column("wd_qid", String(20)),
        Column("wd_label", String(200)),
        Column("egids_status", String(100)),
        Column("writing_systems", String(500)),
        Column("language_family", String(200)),
    )

    metadata.create_all(engine, checkfirst=True)

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE wikidata_languages CASCADE"))
        conn.execute(
            wikidata_languages.insert(),
            df.to_dict(orient="records"),
        )

    print(f"  Loaded {len(df)} rows into wikidata_languages")
    engine.dispose()


def main() -> None:
    project_root = Path.cwd().parents[1]

    input_path = (
        project_root
        / "data"
        / "processed"
        / "glottolog_languages.csv"
    )

    output_path = (
        project_root
        / "data"
        / "processed"
        / "wikidata_languages.csv"
    )

    print(f"Reading ISO codes from {input_path}...")
    glottolog_df = pd.read_csv(input_path, encoding="utf-8")
    iso_codes = glottolog_df["iso639_3"].dropna().astype(str).str.strip().tolist()
    print(f"  {len(iso_codes)} ISO 639-3 codes found")

    print("Querying Wikidata...")
    df = extract_wikidata_languages(iso_codes)
    print(f"  Wikidata returned data for {len(df)} / {len(iso_codes)} languages")

    save_dataframe(df, output_path)

    print(df.head())
    print("Rows:", len(df))
    print(f"Saved to: {output_path}")

    print("Loading to PostgreSQL...")
    load_to_postgres(df, DB_URL)


if __name__ == "__main__":
    main()