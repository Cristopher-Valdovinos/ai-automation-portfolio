"""Group purchase orders into contracts and estimate when each one ends.

A contract is one public body (organismo) + one tender or direct-deal ID.
The end date is estimated with the first rule that applies:
  1. unit_months   - items measured in "Mes": start date + quantity months.
  2. monthly_ended - orders came regularly and then stopped: last order date.
     monthly_active - orders still arriving: contract is running, end unknown.
  3. ai_text       - duration read from the order text by the local LLM
                     (see extract_durations.py), with a quoted evidence.
  4. unknown       - no rule applies.

It also counts urgency signals per public body: emergency purchases and
contract extensions ("prórroga") in the last 6 months usually mean the
contract expired and a new tender is coming.

Usage:
    python src/estimate_contracts.py
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_FILE = DATA_DIR / "contracts.csv"
AI_FILE = DATA_DIR / "ai_durations.jsonl"

MAX_MONTHS = 120          # ignore durations longer than 10 years (likely typos)
MIN_MONTHS = 2            # "1 month" is usually one monthly payment of a longer
                          # contract (e.g. "por el mes de diciembre"), not its duration
INACTIVE_AFTER = 3        # months without orders before a contract is "ended"
MIN_MONTHLY_ORDERS = 3    # distinct months needed to call a contract "monthly"
URGENCY_WINDOW = 6        # months to look back for urgency signals

# Direct-deal IDs look like "2430-4-FTD25" inside the order name.
DEAL_ID_PATTERN = r"(\d+-\d+-[A-Z]+\d{2})"


def load_orders() -> pd.DataFrame:
    files = sorted(RAW_DIR.glob("orders_*.csv.gz"))
    df = pd.concat([pd.read_csv(f, dtype=str) for f in files], ignore_index=True)
    return prepare_orders(df)


def prepare_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Convert text columns to numbers/dates and assign a contract ID."""
    df = df.copy()
    df["amount"] = pd.to_numeric(df["MontoTotalOC_PesosChilenos"].str.replace(",", "."))
    df["quantity"] = pd.to_numeric(df["cantidad"].str.replace(",", "."), errors="coerce")
    df["sent"] = pd.to_datetime(df["FechaEnvio"], errors="coerce")
    df["month"] = df["sent"].dt.to_period("M")

    # Contract ID: tender code, or the direct-deal ID in the name, or the order itself.
    deal_id = df["Nombre"].str.extract(DEAL_ID_PATTERN, expand=False)
    df["contract_id"] = df["CodigoLicitacion"].fillna(deal_id).fillna(df["Codigo"])
    return df


def months_from_units(items: pd.DataFrame) -> pd.Series:
    """Rule 1: largest month quantity per contract, when items are in months."""
    in_months = items[(items["UnidadMedida"] == "Mes") & items["quantity"].between(MIN_MONTHS, MAX_MONTHS)]
    return in_months.groupby(["OrganismoPublico", "contract_id"])["quantity"].max()


def build_contracts(df: pd.DataFrame) -> pd.DataFrame:
    last_data_month = df["month"].max()
    orders = df.drop_duplicates("Codigo")  # one row per order (amount is per order)

    contracts = orders.groupby(["OrganismoPublico", "contract_id"]).agg(
        sector=("sector", "first"),
        region=("RegionUnidadCompra", "first"),
        supplier=("NombreProveedor", lambda s: s.mode().iloc[0]),
        service=("RubroN2", lambda s: s.mode().iloc[0]),
        orders=("Codigo", "count"),
        active_months=("month", "nunique"),
        start=("sent", "min"),
        last_order=("sent", "max"),
        total_amount=("amount", "sum"),
    )
    contracts["months"] = months_from_units(df)
    contracts["end_estimate"] = pd.NaT  # date column, even if no rule matches

    # Rule 1
    by_units = contracts["months"].notna()
    contracts.loc[by_units, "end_estimate"] = [
        start + pd.DateOffset(months=int(m))
        for start, m in zip(contracts.loc[by_units, "start"], contracts.loc[by_units, "months"])
    ]
    contracts["method"] = "unknown"
    contracts.loc[by_units, "method"] = "unit_months"

    # Rule 2
    monthly = ~by_units & (contracts["active_months"] >= MIN_MONTHLY_ORDERS)
    months_since_last = (last_data_month - contracts["last_order"].dt.to_period("M")).apply(lambda x: x.n)
    ended = monthly & (months_since_last > INACTIVE_AFTER)
    contracts.loc[ended, "end_estimate"] = contracts.loc[ended, "last_order"]
    contracts.loc[ended, "method"] = "monthly_ended"
    contracts.loc[monthly & ~ended, "method"] = "monthly_active"

    contracts = contracts.reset_index()
    return apply_ai_durations(contracts)


def apply_ai_durations(contracts: pd.DataFrame) -> pd.DataFrame:
    """Rule 3: use the LLM answers for contracts still unknown."""
    if not AI_FILE.exists():
        return contracts
    from extract_durations import TIME_HINT  # local import avoids a circular import

    ai = pd.read_json(AI_FILE, lines=True).dropna(subset=["ai_months"])
    # Re-check cached answers with the current evidence rule.
    ai = ai[ai["ai_evidence"].str.contains(TIME_HINT) & (ai["ai_months"] >= MIN_MONTHS)]
    contracts = contracts.merge(ai, on=["OrganismoPublico", "contract_id"], how="left")
    use_ai = (contracts["method"] == "unknown") & contracts["ai_months"].notna()
    contracts.loc[use_ai, "months"] = contracts.loc[use_ai, "ai_months"]
    contracts.loc[use_ai, "end_estimate"] = [
        start + pd.DateOffset(months=int(m))
        for start, m in zip(contracts.loc[use_ai, "start"], contracts.loc[use_ai, "ai_months"])
    ]
    contracts.loc[use_ai, "method"] = "ai_text"
    return contracts.drop(columns=["ai_months"])


def urgency_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Emergency purchases and extensions per public body in the last months."""
    since = df["month"].max() - URGENCY_WINDOW
    recent = df[df["month"] > since].drop_duplicates("Codigo")
    origin = recent["ProcedenciaOC"].fillna("")
    recent = recent.assign(
        emergency=origin.str.contains("Emergencia"),
        extension=origin.str.contains("rroga"),
    )
    return recent.groupby("OrganismoPublico")[["emergency", "extension"]].sum()


def main() -> None:
    df = load_orders()
    contracts = build_contracts(df)
    signals = urgency_signals(df)
    contracts = contracts.merge(signals, on="OrganismoPublico", how="left")
    contracts[["emergency", "extension"]] = contracts[["emergency", "extension"]].fillna(0).astype(int)

    contracts.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    summary = contracts.groupby("method").agg(
        contracts=("contract_id", "count"),
        amount_share=("total_amount", "sum"),
    )
    summary["contract_share"] = (summary["contracts"] / len(contracts) * 100).round(1)
    summary["amount_share"] = (summary["amount_share"] / contracts["total_amount"].sum() * 100).round(1)
    print(f"{len(contracts):,} contracts -> {OUTPUT_FILE.name}")
    print(summary.sort_values("amount_share", ascending=False).to_string())
    print(f"public bodies with urgency signals: {(signals.sum(axis=1) > 0).sum()}")


if __name__ == "__main__":
    main()
