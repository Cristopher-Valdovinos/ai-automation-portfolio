import xml.etree.ElementTree as ET

import pandas as pd

from charts import backtest_chart, hbar_chart, prospects_chart, short_name

SVG = "{http://www.w3.org/2000/svg}"


def test_hbar_chart_is_valid_svg_and_escapes_text():
    svg = hbar_chart("Título <A&B>", "sub", [("Uno & dos", 10, "10%"), ("Tres", 5, "5%")], max_value=10,
                     reference=(4, "Al azar: 4%"), note="nota")
    root = ET.fromstring(svg)  # raises if the XML is broken

    assert len(root.findall(f"{SVG}path")) == 2           # one bar per row
    assert root.find(f"{SVG}title").text == "Título <A&B>"
    assert "prefers-color-scheme: dark" in svg             # dark mode support


def test_bar_widths_follow_values():
    root = ET.fromstring(hbar_chart("t", "s", [("a", 10, "10"), ("b", 5, "5")], max_value=10))
    ends = [float(p.get("d").split("H")[1].split()[0]) for p in root.findall(f"{SVG}path")]
    assert ends[0] > ends[1]


def test_short_name():
    assert short_name("I MUNICIPALIDAD DE LAS CABRAS") == "Municipalidad de Las Cabras"
    assert short_name("ILUSTRE MUNICIPALIDAD DE MELIPILLA") == "Municipalidad de Melipilla"
    assert short_name("X" * 50).endswith("…") and len(short_name("X" * 50)) == 36


def test_backtest_chart_sorts_rows():
    breakdown = pd.DataFrame([
        {"group": "Estado", "value": "por vencer", "precision": 0.6},
        {"group": "Estado", "value": "ya vencido", "precision": 0.4},
        {"group": "Señales de urgencia", "value": "sí", "precision": 0.5},
        {"group": "Puntaje", "value": "70 o más", "precision": 0.7},
    ])
    summary = {"precision": 0.55, "baseline": 0.3, "cutoffs": 3, "prospects": 1200}
    root = ET.fromstring(backtest_chart(summary, breakdown))
    values = [t.text for t in root.iter(f"{SVG}text") if t.get("class") == "value"]

    assert values == ["70%", "60%", "55%", "50%", "40%"]


def test_prospects_chart_shows_top_10():
    prospects = pd.DataFrame({
        "OrganismoPublico": [f"I MUNICIPALIDAD {i}" for i in range(12)],
        "total_amount": [100_000_000 + i for i in range(12)],
        "days_to_end": [5, -3] * 6,
    })
    root = ET.fromstring(prospects_chart(prospects, "17-11-2026"))
    values = [t.text for t in root.iter(f"{SVG}text") if t.get("class") == "value"]

    assert len(values) == 10
    assert values[0] == "$100 M · vence en 5 días" and values[1] == "$100 M · venció hace 3 días"
