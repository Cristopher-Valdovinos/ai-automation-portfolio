"""Backtest: how often do the prospects really sign a new contract?

For each cutoff date in the past:
  1. Keep only the orders sent before the cutoff (what we knew that day).
  2. Build the prospect list exactly as the weekly report does.
  3. Look at the real data after the cutoff: a prospect is a "hit" if the
     same public body started a new contract for the same service within
     HORIZON_DAYS, worth at least MIN_NEW_AMOUNT.

Metrics:
  - precision:      hits / prospects
  - precision_top:  the same for the TOP_N prospects with the highest score
  - baseline:       share of all buyers with a large contract (same service)
                    that signed a new one in the same period (random pick)
  - lift:           precision / baseline
  - coverage:       share of large new contracts (from buyers with history)
                    that were in the prospect list
  - timing error:   median days between estimated end and real new start

Usage:
    python src/backtest.py
"""

from pathlib import Path

import pandas as pd

from estimate_contracts import estimate, load_orders
from weekly_report import MIN_AMOUNT, WINDOW_DAYS, find_prospects

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
RESULTS_FILE = DATA_DIR / "backtest_by_cutoff.csv"
SUMMARY_FILE = DOCS_DIR / "backtest.md"

FIRST_CUTOFF = "2025-01-01"
LAST_CUTOFF = "2026-07-01"
HORIZON_DAYS = 120
MIN_NEW_AMOUNT = MIN_AMOUNT / 2  # a renewal can be smaller than the old contract
TOP_N = 25

KEY = ["OrganismoPublico", "service"]


def new_contracts(all_contracts: pd.DataFrame, cutoff: pd.Timestamp, days: int,
                  min_amount: float) -> pd.DataFrame:
    """Contracts that started after the cutoff, within `days`."""
    end = cutoff + pd.Timedelta(days=days)
    started = all_contracts["start"].between(cutoff, end, inclusive="right")
    return all_contracts[started & (all_contracts["total_amount"] >= min_amount)]


def evaluate_cutoff(orders: pd.DataFrame, all_contracts: pd.DataFrame,
                    cutoff: pd.Timestamp) -> tuple[dict, pd.DataFrame]:
    """Return the metrics for one cutoff and its prospects with a 'hit' column."""
    known = estimate(orders[orders["sent"] < cutoff])
    prospects = find_prospects(known, cutoff)

    events = new_contracts(all_contracts, cutoff, HORIZON_DAYS, MIN_NEW_AMOUNT)
    first_start = events.groupby(KEY)["start"].min()

    prospects = prospects.join(first_start.rename("new_start"), on=KEY)
    prospects["hit"] = prospects["new_start"].notna()
    top = prospects.head(TOP_N)

    # Baseline: every buyer+service with a large contract before the cutoff.
    population = known[known["total_amount"] >= MIN_AMOUNT][KEY].drop_duplicates()
    population = population.join(first_start.rename("new_start"), on=KEY)
    baseline = population["new_start"].notna().mean()

    # Coverage: large new contracts (within the report window) from buyers
    # with history, that the report had listed.
    large = new_contracts(all_contracts, cutoff, WINDOW_DAYS, MIN_AMOUNT)
    large_keys = large[KEY].drop_duplicates().merge(population[KEY], on=KEY)
    listed = large_keys.merge(prospects[KEY].drop_duplicates(), on=KEY)

    hits = prospects[prospects["hit"]]
    timing_error = (hits["new_start"] - hits["end_estimate"]).dt.days.abs()

    metrics = {
        "cutoff": cutoff.date(),
        "prospects": len(prospects),
        "hits": int(prospects["hit"].sum()),
        "top_prospects": len(top),
        "top_hits": int(top["hit"].sum()),
        "population": len(population),
        "population_hits": int(population["new_start"].notna().sum()),
        "baseline": round(baseline, 3),
        "large_new": len(large_keys),
        "large_new_listed": len(listed),
        "timing_error_median": timing_error.median(),
    }
    return metrics, prospects


def breakdown(prospects: pd.DataFrame) -> pd.DataFrame:
    """Precision by type of prospect, over all cutoffs."""
    groups = {
        "Estado": prospects["days_to_end"].apply(lambda d: "ya vencido" if d < 0 else "por vencer"),
        "Señales de urgencia": prospects["urgency"].gt(0).map({True: "sí", False: "no"}),
        "Puntaje": pd.cut(prospects["score"], [-1, 49, 69, 100], labels=["menos de 50", "50 a 69", "70 o más"]),
        "Origen de la fecha": prospects["method"].map(
            {"unit_months": "campos de la orden", "ai_text": "leída por la IA", "monthly_ended": "órdenes mensuales"}
        ),
    }
    rows = []
    for name, labels in groups.items():
        stats = prospects.groupby(labels, observed=True)["hit"].agg(["mean", "count"])
        rows += [{"group": name, "value": value, "precision": s["mean"], "prospects": int(s["count"])}
                 for value, s in stats.iterrows()]
    return pd.DataFrame(rows)


def summarize(results: pd.DataFrame) -> dict:
    precision = results["hits"].sum() / results["prospects"].sum()
    precision_top = results["top_hits"].sum() / results["top_prospects"].sum()
    baseline = results["population_hits"].sum() / results["population"].sum()
    return {
        "cutoffs": len(results),
        "prospects": int(results["prospects"].sum()),
        "precision": precision,
        "precision_top": precision_top,
        "baseline": baseline,
        "lift": precision / baseline,
        "lift_top": precision_top / baseline,
        "coverage": results["large_new_listed"].sum() / results["large_new"].sum(),
        "timing_error_median": results["timing_error_median"].median(),
    }


def pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def times(value: float) -> str:
    """1.8 -> '1,8x' (Chilean decimal comma)."""
    return f"{value:.1f}x".replace(".", ",")


def to_markdown(summary: dict, results: pd.DataFrame, by_type: pd.DataFrame) -> str:
    n_prospects = f"{summary['prospects']:,}".replace(",", ".")
    type_rows = "\n".join(
        f"| {r.group} | {r.value} | {pct(r.precision)} | {r.prospects} |" for r in by_type.itertuples()
    )
    rows = "\n".join(
        f"| {r.cutoff} | {r.prospects} | {r.hits} | {pct(r.hits / r.prospects) if r.prospects else '—'} "
        f"| {pct(r.baseline)} |"
        for r in results.itertuples()
    )
    return f"""# Backtest del radar

Se generó el reporte en {summary['cutoffs']} fechas pasadas (el día 1 de cada mes, de {FIRST_CUTOFF} a {LAST_CUTOFF}), usando solo los datos disponibles en cada fecha. Luego se revisó con los datos reales si cada organismo empezó un **contrato nuevo del mismo servicio** (de al menos ${MIN_NEW_AMOUNT / 1e6:.0f} M) dentro de los {HORIZON_DAYS} días siguientes.

## Resultado

| Métrica | Valor |
|---|---|
| Prospectos evaluados | {n_prospects} |
| **Precisión** (prospectos que contrataron de nuevo) | **{pct(summary['precision'])}** |
| **Precisión del top {TOP_N}** | **{pct(summary['precision_top'])}** |
| Línea base (elegir al azar entre compradores con contratos grandes) | {pct(summary['baseline'])} |
| **Mejora sobre el azar** | **{times(summary['lift'])}** (top {TOP_N}: {times(summary['lift_top'])}) |
| Cobertura (contratos grandes nuevos que el reporte anticipó) | {pct(summary['coverage'])} |
| Error típico de fecha (mediana) | {summary['timing_error_median']:.0f} días |

## Qué prospectos aciertan más

| Grupo | Valor | Precisión | Prospectos |
|---|---|---|---|
{type_rows}

## Por fecha

| Fecha | Prospectos | Aciertos | Precisión | Línea base |
|---|---|---|---|---|
{rows}

## Cómo leerlo

- Un **acierto** significa que el organismo volvió a contratar el servicio en el plazo; no dice qué proveedor ganó.
- La **línea base** responde: si un vendedor eligiera al azar entre todos los organismos que tienen contratos grandes de ese servicio, ¿cuántos contratarían en el mismo plazo?
- Un mismo contrato puede aparecer en varias fechas seguidas (el reporte mira ±{WINDOW_DAYS} días), así que las fechas no son independientes.
- Las duraciones leídas por la IA vienen del texto de cada orden, que existía desde su creación: no usan información del futuro.
"""


def main() -> None:
    orders = load_orders()
    all_contracts = estimate(orders)

    cutoffs = pd.date_range(FIRST_CUTOFF, LAST_CUTOFF, freq="MS")
    results, all_prospects = [], []
    for cutoff in cutoffs:
        row, prospects = evaluate_cutoff(orders, all_contracts, cutoff)
        results.append(row)
        all_prospects.append(prospects)
        print(f"{row['cutoff']}: {row['hits']}/{row['prospects']} hits, baseline {row['baseline']:.0%}")
    results = pd.DataFrame(results)
    results.to_csv(RESULTS_FILE, index=False)
    by_type = breakdown(pd.concat(all_prospects, ignore_index=True))

    summary = summarize(results)
    DOCS_DIR.mkdir(exist_ok=True)
    SUMMARY_FILE.write_text(to_markdown(summary, results, by_type), encoding="utf-8")
    print(f"\nprecision {summary['precision']:.0%} (top {TOP_N}: {summary['precision_top']:.0%}) | "
          f"baseline {summary['baseline']:.0%} | lift {summary['lift']:.1f}x | "
          f"coverage {summary['coverage']:.0%} | timing error {summary['timing_error_median']:.0f} days")


if __name__ == "__main__":
    main()
