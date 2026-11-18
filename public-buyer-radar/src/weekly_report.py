"""Build the weekly list of sales prospects from contracts.csv.

A prospect is a contract that:
  - ends (or ended) within WINDOW_DAYS of the report date,
  - is worth at least MIN_AMOUNT,
  - has not been renewed yet: the same public body has no newer contract
    for the same service.

Each prospect gets a 0-100 score that is easy to explain:
  - 50 points: contract size (percentile among the prospects)
  - 30 points: timing (the closer the end date, the more points)
  - 20 points: urgency signals (recent emergency purchases or extensions)

Usage:
    python src/weekly_report.py                 # report date = today
    python src/weekly_report.py --date 2026-11-17
"""

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONTRACTS_FILE = DATA_DIR / "contracts.csv"
REPORTS_DIR = DATA_DIR / "reports"

WINDOW_DAYS = 90
MIN_AMOUNT = 50_000_000
RENEWAL_MARGIN_DAYS = 60   # a new contract starting this close to the end counts as renewal
TOP_IN_MARKDOWN = 25

CONFIDENCE = {
    "unit_months": "alta",
    "ai_text": "media",
    "monthly_ended": "media",
}


def load_contracts() -> pd.DataFrame:
    return pd.read_csv(CONTRACTS_FILE, parse_dates=["start", "last_order", "end_estimate"])


def is_renewed(contract: pd.Series, all_contracts: pd.DataFrame) -> bool:
    same_buyer_service = all_contracts[
        (all_contracts["OrganismoPublico"] == contract["OrganismoPublico"])
        & (all_contracts["service"] == contract["service"])
        & (all_contracts["contract_id"] != contract["contract_id"])
    ]
    limit = contract["end_estimate"] - pd.Timedelta(days=RENEWAL_MARGIN_DAYS)
    return bool((same_buyer_service["start"] >= limit).any())


def find_prospects(contracts: pd.DataFrame, report_date: pd.Timestamp) -> pd.DataFrame:
    window = pd.Timedelta(days=WINDOW_DAYS)
    candidates = contracts[
        contracts["end_estimate"].between(report_date - window, report_date + window)
        & (contracts["total_amount"] >= MIN_AMOUNT)
    ].copy()

    renewed = candidates.apply(is_renewed, axis=1, all_contracts=contracts)
    prospects = candidates[~renewed].copy()

    prospects["days_to_end"] = (prospects["end_estimate"] - report_date).dt.days
    prospects["urgency"] = prospects["emergency"] + prospects["extension"]

    size_points = prospects["total_amount"].rank(pct=True) * 50
    timing_points = (1 - prospects["days_to_end"].abs() / WINDOW_DAYS) * 30
    urgency_points = (prospects["urgency"] > 0) * 20
    prospects["score"] = (size_points + timing_points + urgency_points).round().astype(int)

    prospects["status"] = prospects["days_to_end"].apply(
        lambda d: f"venció hace {-d} días, sin renovación visible" if d < 0 else f"vence en {d} días"
    )
    prospects["confidence"] = prospects["method"].map(CONFIDENCE)
    return prospects.sort_values("score", ascending=False)


def millions(amount: float) -> str:
    return f"${amount / 1e6:,.0f} M".replace(",", ".")


def to_markdown(prospects: pd.DataFrame, report_date: pd.Timestamp) -> str:
    lines = [
        f"# Radar de compradores públicos — {report_date:%d-%m-%Y}",
        "",
        "Contratos de servicios de limpieza industrial (aseo y residuos) que vencen "
        f"o vencieron en ±{WINDOW_DAYS} días, sobre {millions(MIN_AMOUNT)}, "
        "y que todavía no muestran renovación.",
        "",
        f"- Prospectos: **{len(prospects)}**",
        f"- Monto total de los contratos que vencen: **{millions(prospects['total_amount'].sum())}**",
        f"- Con señales de urgencia: **{(prospects['urgency'] > 0).sum()}**",
        "",
        f"## Top {min(TOP_IN_MARKDOWN, len(prospects))}",
        "",
        "| # | Puntaje | Organismo | Región | Servicio | Proveedor actual | Monto contrato | Estado | Confianza | Urgencia |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(prospects.head(TOP_IN_MARKDOWN).itertuples(), start=1):
        urgency = f"{row.emergency} emerg. / {row.extension} prórr." if row.urgency else "—"
        lines.append(
            f"| {i} | {row.score} | {row.OrganismoPublico} | {row.region} | {row.service} | "
            f"{row.supplier} | {millions(row.total_amount)} | {row.status} | {row.confidence} | {urgency} |"
        )
    lines += [
        "",
        "## Cómo leer este reporte",
        "",
        "- **Puntaje (0-100):** 50 puntos por tamaño del contrato, 30 por cercanía del vencimiento "
        "y 20 si el organismo hizo compras de emergencia o prórrogas en los últimos 6 meses.",
        "- **Confianza alta:** la duración viene en los datos de la orden (meses). "
        "**Media:** la leyó la IA desde el texto, o se infiere porque dejaron de llegar órdenes mensuales.",
        "- Las fechas son estimaciones a partir de datos abiertos de ChileCompra; conviene confirmar en la ficha de la licitación.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()), help="report date, YYYY-MM-DD")
    args = parser.parse_args()
    report_date = pd.Timestamp(args.date)

    prospects = find_prospects(load_contracts(), report_date)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_file = REPORTS_DIR / f"prospects_{report_date:%Y-%m-%d}.csv"
    md_file = REPORTS_DIR / f"prospects_{report_date:%Y-%m-%d}.md"
    prospects.to_csv(csv_file, index=False, encoding="utf-8")
    md_file.write_text(to_markdown(prospects, report_date), encoding="utf-8")
    print(f"{len(prospects)} prospects -> {csv_file.name}, {md_file.name}")


if __name__ == "__main__":
    main()
