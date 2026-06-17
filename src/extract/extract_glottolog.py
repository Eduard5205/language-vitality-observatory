from pathlib import Path
import os
import configparser
import pandas as pd


def clean_multiline_value(value: str) -> str:
    return ",".join(
        line.strip()
        for line in value.splitlines()
        if line.strip()
    )


def parse_glottolog_file(ini_path: Path) -> dict | None:
    config = configparser.ConfigParser()
    config.read(ini_path, encoding="utf-8")

    if "core" not in config:
        return None

    level = config.get("core", "level", fallback=None)
    if level != "language":
        return None

    iso_code = config.get("core", "iso639-3", fallback=None)
    if not iso_code:
        return None

    countries = clean_multiline_value(
        config.get("core", "countries", fallback="")
    )

    macroareas = clean_multiline_value(
        config.get("core", "macroareas", fallback="")
    )

    return {
        "glottocode": ini_path.parent.name,
        "name": config.get("core", "name", fallback=None),
        "level": level,
        "countries": countries,
        "macroareas": macroareas,
        "latitude": config.get("core", "latitude", fallback=None),
        "longitude": config.get("core", "longitude", fallback=None),
        "iso639_3": iso_code,
        "status": config.get("endangerment", "status", fallback=None),
    }


def extract_glottolog_languages(root: Path) -> pd.DataFrame:
    rows = []

    for folder, subfolders, files in os.walk(root):
        if "md.ini" not in files:
            continue

        ini_path = Path(folder) / "md.ini"
        row = parse_glottolog_file(ini_path)

        if row is not None:
            rows.append(row)

    return pd.DataFrame(rows)


def save_dataframe(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8")


def main() -> None:
    project_root = Path.cwd().parents[1]

    input_root = (
        project_root
        / "data"
        / "raw"
        / "glottolog"
        / "languoids"
        / "tree"
    )

    output_path = (
        project_root
        / "data"
        / "processed"
        / "glottolog_languages_test.csv"
    )

    df = extract_glottolog_languages(input_root)
    save_dataframe(df, output_path)

    print(df.head())
    print("Rows:", len(df))
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
