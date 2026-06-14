from pathlib import Path
import os
import configparser
import pandas as pd

PROJECT_ROOT = Path.cwd().parents[1]

root = PROJECT_ROOT / "data" / "raw" / "glottolog" / "languoids" / "tree"

rows = []

for folder, subfolders, files in os.walk(root):

    if "md.ini" not in files:
        continue

    ini_path = Path(folder) / "md.ini"

    config = configparser.ConfigParser()
    config.read(ini_path, encoding="utf-8")

    if "core" not in config:
        continue
    
    
    iso_code = config.get("core", "iso639-3", fallback=None)
    
    if not iso_code:
        continue
    
    countries = config.get("core", "countries", fallback="")

    countries = ",".join(
    line.strip()
    for line in countries.splitlines()
    if line.strip()
)

    macroareas = config.get("core", "macroareas", fallback="")

    macroareas = ",".join(
    line.strip()
    for line in macroareas.splitlines()
    if line.strip()
)

    rows.append({
        "glottocode": ini_path.parent.name,
        "name": config.get("core", "name", fallback=None),
        "level": config.get("core", "level", fallback=None),
        "countries": countries,
        "macroareas": macroareas,
        "latitude": config.get("core", "latitude", fallback=None),
        "longitude": config.get("core", "longitude", fallback=None),
        "iso639_3": config.get("core", "iso639-3", fallback=None),
        "status": config.get("endangerment", "status", fallback=None)      
    })

df = pd.DataFrame(rows)

processed_dir = PROJECT_ROOT / "data" / "processed"
processed_dir.mkdir(parents=True, exist_ok=True)

output_path = processed_dir / "glottolog_languages.csv"

df.to_csv(output_path, index=False, encoding="utf-8")

print(df.head())
print("Rows:", len(df))
print(f"Saved to: {output_path}")
