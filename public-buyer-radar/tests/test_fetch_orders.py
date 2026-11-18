import zipfile

import pandas as pd

import fetch_orders
from fetch_orders import CATEGORY, COLUMNS, filter_csv, month_range, process_month


def make_zip(path, categories: list[str]):
    """Write a tiny ChileCompra-like zip: latin1, ';' separated, quoted fields."""
    header = ";".join(f'"{c}"' for c in COLUMNS + ["OtraColumna"])
    lines = [header]
    for i, category in enumerate(categories):
        values = {c: f"valor {i}" for c in COLUMNS}
        values["Codigo"] = f"OC-{i}"
        values["RubroN1"] = category
        values["Nombre"] = "Recolección de basura\nsegunda línea"  # accent and newline inside a field
        lines.append(";".join(f'"{values[c]}"' for c in COLUMNS) + ';"x"')
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("2026-10.csv", "\r\n".join(lines).encode("latin1"))


def test_month_range_crosses_years():
    assert month_range("2025-11", "2026-02") == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]


def test_filter_csv_keeps_only_the_category(tmp_path):
    zip_path = tmp_path / "month.zip"
    make_zip(zip_path, [CATEGORY, "Alimentos, bebidas y tabaco", CATEGORY])

    df = filter_csv(zip_path)

    assert list(df["Codigo"]) == ["OC-0", "OC-2"]
    assert list(df.columns) == COLUMNS  # extra columns are not read
    assert df.loc[0, "Nombre"] == "Recolección de basura\nsegunda línea"


def test_process_month_writes_file_and_skips_when_done(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch_orders, "OUTPUT_DIR", tmp_path / "raw")
    zip_path = tmp_path / "month.zip"
    make_zip(zip_path, [CATEGORY])

    out_file = process_month(2026, 10, zip_path)
    assert out_file.name == "orders_2026-10.csv.gz"
    assert len(pd.read_csv(out_file)) == 1

    process_month(2026, 10, zip_path)
    assert "already done" in capsys.readouterr().out

    process_month(2026, 10, zip_path, refresh=True)  # current month: download again
    assert "1 orders" in capsys.readouterr().out
