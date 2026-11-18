"""Draw the README charts as SVG files, with no plotting library.

Two horizontal bar charts:
  - backtest_precision.svg: how often each type of prospect re-contracts,
    against the random baseline.
  - top_prospects.svg: the 10 best prospects of the latest report.

The SVG files adapt to light and dark mode and render directly on GitHub.

Usage:
    python src/charts.py
"""

import json
from html import escape
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CHARTS_DIR = ROOT / "docs" / "charts"

# Colors: one hue (single series) plus text and grid tokens, light and dark.
STYLE = """
  .surface { fill: #fcfcfb; }
  .bar { fill: #2a78d6; }
  .title { fill: #0b0b0b; font: 600 17px system-ui, -apple-system, 'Segoe UI', sans-serif; }
  .subtitle, .label { fill: #52514e; font: 13px system-ui, -apple-system, 'Segoe UI', sans-serif; }
  .value { fill: #0b0b0b; font: 600 13px system-ui, -apple-system, 'Segoe UI', sans-serif; }
  .note { fill: #898781; font: 12px system-ui, -apple-system, 'Segoe UI', sans-serif; }
  .axis { stroke: #898781; stroke-width: 1; }
  .reference { stroke: #52514e; stroke-width: 1.5; stroke-dasharray: 4 4; }
  @media (prefers-color-scheme: dark) {
    .surface { fill: #1a1a19; }
    .bar { fill: #3987e5; }
    .title, .value { fill: #f0efec; }
    .subtitle, .label { fill: #c3c2b7; }
    .reference { stroke: #c3c2b7; }
  }
"""

WIDTH = 760
LABEL_WIDTH = 270     # left column for category names
VALUE_SPACE = 225     # right space for the value text
BAR_HEIGHT = 22
BAR_GAP = 12
TOP = 78              # space for title and subtitle
RADIUS = 4            # rounded data-end only


def bar_path(x: float, y: float, width: float, height: float) -> str:
    """Bar anchored on the left (square) with a rounded right end."""
    r = min(RADIUS, width / 2, height / 2)
    return (f"M{x:.1f},{y:.1f} H{x + width - r:.1f} Q{x + width:.1f},{y:.1f} {x + width:.1f},{y + r:.1f} "
            f"V{y + height - r:.1f} Q{x + width:.1f},{y + height:.1f} {x + width - r:.1f},{y + height:.1f} "
            f"H{x:.1f} Z")


def hbar_chart(title: str, subtitle: str, rows: list[tuple[str, float, str]], max_value: float,
               reference: tuple[float, str] | None = None, note: str = "") -> str:
    """rows: (label, value, value_text). Returns the SVG as text."""
    plot_width = WIDTH - LABEL_WIDTH - VALUE_SPACE
    height = TOP + len(rows) * (BAR_HEIGHT + BAR_GAP) + (56 if reference else 30) + (18 if note else 0)
    scale = plot_width / max_value
    x0 = LABEL_WIDTH

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="t d">',
        f'<title id="t">{escape(title)}</title>',
        f'<desc id="d">{escape(subtitle)}. ' + "; ".join(escape(f"{l}: {t}") for l, _, t in rows) + "</desc>",
        f"<style>{STYLE}</style>",
        f'<rect class="surface" width="{WIDTH}" height="{height}" rx="8"/>',
        f'<text class="title" x="24" y="34">{escape(title)}</text>',
        f'<text class="subtitle" x="24" y="56">{escape(subtitle)}</text>',
    ]
    y = TOP
    for label, value, value_text in rows:
        width = max(value * scale, 1)
        mid = y + BAR_HEIGHT / 2 + 4.5
        parts.append(f'<text class="label" x="{x0 - 12}" y="{mid:.1f}" text-anchor="end">{escape(label)}</text>')
        parts.append(f'<path class="bar" d="{bar_path(x0, y, width, BAR_HEIGHT)}"/>')
        parts.append(f'<text class="value" x="{x0 + width + 8:.1f}" y="{mid:.1f}">{escape(value_text)}</text>')
        y += BAR_HEIGHT + BAR_GAP
    bottom = y - BAR_GAP + 6
    parts.append(f'<line class="axis" x1="{x0}" y1="{TOP - 6}" x2="{x0}" y2="{bottom}"/>')

    if reference:
        ref_value, ref_label = reference
        rx = x0 + ref_value * scale
        parts.append(f'<line class="reference" x1="{rx:.1f}" y1="{TOP - 6}" x2="{rx:.1f}" y2="{bottom}"/>')
        parts.append(f'<text class="label" x="{rx:.1f}" y="{bottom + 18}" text-anchor="middle">'
                     f"{escape(ref_label)}</text>")
        bottom += 24
    if note:
        parts.append(f'<text class="note" x="24" y="{bottom + 22}">{escape(note)}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def backtest_chart(summary: dict, breakdown: pd.DataFrame) -> str:
    def precision(group: str, value: str) -> float:
        match = breakdown[(breakdown["group"] == group) & (breakdown["value"] == value)]
        return float(match["precision"].iloc[0])

    rows = [
        ("Contrato por vencer", precision("Estado", "por vencer")),
        ("Con señales de urgencia", precision("Señales de urgencia", "sí")),
        ("Puntaje 70 o más", precision("Puntaje", "70 o más")),
        ("Todos los prospectos", summary["precision"]),
        ("Contrato ya vencido", precision("Estado", "ya vencido")),
    ]
    rows.sort(key=lambda row: row[1], reverse=True)
    return hbar_chart(
        title="¿Cuántos prospectos vuelven a contratar en 4 meses?",
        subtitle=f"Backtest en {summary['cutoffs']} fechas pasadas, "
                 f"{summary['prospects']:,} prospectos evaluados".replace(",", "."),
        rows=[(label, value, pct(value)) for label, value in rows],
        max_value=0.8,
        reference=(summary["baseline"], f"Al azar: {pct(summary['baseline'])}"),
        note="Acierto: el organismo inició un contrato nuevo del mismo servicio en 120 días.",
    )


# Articles (La, Las, Los, El) stay capitalized: they are often part of a
# place name (Las Cabras, La Florida, Los Ángeles).
SMALL_WORDS = {"de", "del", "y", "para", "al", "en"}


def short_name(name: str, limit: int = 36) -> str:
    """'I MUNICIPALIDAD DE LINARES' -> 'Municipalidad de Linares'."""
    words = name.split()
    if words and words[0].upper() in {"I", "ILUSTRE"}:
        words = words[1:]
    name = " ".join(w.lower() if i and w.lower() in SMALL_WORDS else w.capitalize() for i, w in enumerate(words))
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


def millions(amount: float) -> str:
    return f"${amount / 1e6:,.0f} M".replace(",", ".")


def prospects_chart(prospects: pd.DataFrame, report_date: str) -> str:
    top = prospects.head(10)
    rows = []
    for row in top.itertuples():
        when = f"vence en {row.days_to_end} días" if row.days_to_end >= 0 else f"venció hace {-row.days_to_end} días"
        rows.append((short_name(row.OrganismoPublico), row.total_amount / 1e6,
                     f"{millions(row.total_amount)} · {when}"))
    return hbar_chart(
        title="Top 10 prospectos de la semana",
        subtitle=f"Monto del contrato que vence · reporte del {report_date}",
        rows=rows,
        max_value=max(value for _, value, _ in rows),
        note="Ordenados por puntaje (tamaño, cercanía del vencimiento y señales de urgencia).",
    )


def latest_report() -> Path:
    reports = sorted(p for p in (DATA_DIR / "reports").glob("prospects_*.csv") if p.stem.count("_") == 1)
    return reports[-1]


def main() -> None:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    summary = json.loads((DATA_DIR / "backtest_summary.json").read_text(encoding="utf-8"))
    breakdown = pd.read_csv(DATA_DIR / "backtest_breakdown.csv")
    (CHARTS_DIR / "backtest_precision.svg").write_text(backtest_chart(summary, breakdown), encoding="utf-8")

    report = latest_report()
    report_date = pd.Timestamp(report.stem.split("_")[1]).strftime("%d-%m-%Y")
    prospects = pd.read_csv(report)
    (CHARTS_DIR / "top_prospects.svg").write_text(prospects_chart(prospects, report_date), encoding="utf-8")
    print(f"charts -> {CHARTS_DIR.relative_to(ROOT)} (report {report.name})")


if __name__ == "__main__":
    main()
