"""Download monthly purchase orders from ChileCompra and keep one category.

Each month is a ~100 MB zip with a ~800 MB CSV inside. We read the CSV in
chunks, keep only the rows of the chosen category and save a small
compressed file per month. The big files are deleted afterwards.

Usage:
    python src/fetch_orders.py 2024-01 2026-10
    python src/fetch_orders.py 2026-10 2026-10 --zip path/to/2026-10.zip
"""

import argparse
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

BASE_URL = "https://transparenciachc.blob.core.windows.net/oc-da/{year}-{month}.zip"
CATEGORY = "Servicios de limpieza industrial"  # value of the RubroN1 column
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

COLUMNS = [
    "Codigo", "Nombre", "Descripcion/Obervaciones", "ProcedenciaOC",
    "EsTratoDirecto", "EsCompraAgil", "Estado", "FechaCreacion", "FechaEnvio",
    "MontoTotalOC_PesosChilenos", "CodigoOrganismoPublico", "OrganismoPublico",
    "sector", "UnidadCompra", "RegionUnidadCompra", "CodigoProveedor",
    "NombreProveedor", "RegionProveedor", "CodigoLicitacion", "RubroN1",
    "RubroN2", "RubroN3", "NombreroductoGenerico", "cantidad", "UnidadMedida",
    "totalLineaNeto",
]


def month_range(start: str, end: str) -> list[tuple[int, int]]:
    """Return (year, month) pairs from start to end, both 'YYYY-MM'."""
    periods = pd.period_range(start, end, freq="M")
    return [(p.year, p.month) for p in periods]


def filter_csv(zip_path: Path) -> pd.DataFrame:
    """Read the CSV inside the zip in chunks and keep only CATEGORY rows."""
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            chunks = pd.read_csv(
                f, sep=";", encoding="latin1", usecols=COLUMNS,
                dtype=str, chunksize=200_000,
            )
            kept = [chunk[chunk["RubroN1"] == CATEGORY] for chunk in chunks]
    return pd.concat(kept, ignore_index=True)


def process_month(year: int, month: int, zip_path: Path | None = None, refresh: bool = False) -> Path:
    """Download and filter one month. refresh=True re-downloads a month that
    already exists (the current month grows every day)."""
    out_file = OUTPUT_DIR / f"orders_{year}-{month:02d}.csv.gz"
    if out_file.exists() and not refresh:
        print(f"{year}-{month:02d}: already done, skipping")
        return out_file

    with tempfile.TemporaryDirectory() as tmp:
        if zip_path is None:
            url = BASE_URL.format(year=year, month=month)
            print(f"{year}-{month:02d}: downloading {url}")
            zip_path = Path(tmp) / "month.zip"
            urllib.request.urlretrieve(url, zip_path)
        df = filter_csv(zip_path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_file, index=False, encoding="utf-8")
    print(f"{year}-{month:02d}: {len(df):,} rows, "
          f"{df['Codigo'].nunique():,} orders -> {out_file.name}")
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start", help="first month, YYYY-MM")
    parser.add_argument("end", help="last month, YYYY-MM")
    parser.add_argument("--zip", type=Path, help="use a local zip (one month only)")
    args = parser.parse_args()

    for year, month in month_range(args.start, args.end):
        process_month(year, month, args.zip)


if __name__ == "__main__":
    main()
