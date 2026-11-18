import json

import pandas as pd

import estimate_contracts
from estimate_contracts import build_contracts, urgency_signals


def contract(contracts: pd.DataFrame, contract_id: str) -> pd.Series:
    return contracts.set_index("contract_id").loc[contract_id]


# A recent order from another buyer, so the data ends in October 2026.
LAST_MONTH = {"Codigo": "Z-1", "FechaEnvio": "2026-10-15", "CodigoLicitacion": "999-1-LR26",
              "OrganismoPublico": "OTRO ORGANISMO"}


def test_prepare_orders_parses_amount_and_contract_id(make_orders):
    df = make_orders([
        {"Codigo": "A-1", "FechaEnvio": "2025-01-10", "MontoTotalOC_PesosChilenos": "1500,5"},
        {"Codigo": "B-1", "FechaEnvio": "2025-01-10", "CodigoLicitacion": None,
         "Nombre": "Orden de Compra generada por Trato Directo ID 2430-4-FTD25"},
        {"Codigo": "C-1", "FechaEnvio": "2025-01-10", "CodigoLicitacion": None, "Nombre": "Compra menor"},
    ]).set_index("Codigo")

    assert df.loc["A-1", "amount"] == 1500.5
    assert df.loc["A-1", "contract_id"] == "100-1-LR24"   # tender code
    assert df.loc["B-1", "contract_id"] == "2430-4-FTD25"  # direct-deal ID in the name
    assert df.loc["C-1", "contract_id"] == "C-1"           # the order itself


def test_unit_months_rule(make_orders):
    df = make_orders([
        {"Codigo": "A-1", "FechaEnvio": "2025-01-10", "cantidad": "12", "UnidadMedida": "Mes"},
        LAST_MONTH,
    ])
    row = contract(build_contracts(df), "100-1-LR24")

    assert row["method"] == "unit_months"
    assert row["end_estimate"] == pd.Timestamp("2026-01-10")


def test_one_month_is_not_a_contract_duration(make_orders):
    df = make_orders([
        {"Codigo": "A-1", "FechaEnvio": "2025-01-10", "cantidad": "1", "UnidadMedida": "Mes"},
        LAST_MONTH,
    ])
    row = contract(build_contracts(df), "100-1-LR24")

    assert row["method"] == "unknown"
    assert pd.isna(row["end_estimate"])


def test_monthly_orders_that_stopped_are_ended(make_orders):
    months = ["2025-01-05", "2025-02-05", "2025-03-05", "2025-04-05"]
    df = make_orders([{"Codigo": f"A-{i}", "FechaEnvio": d} for i, d in enumerate(months)] + [LAST_MONTH])
    row = contract(build_contracts(df), "100-1-LR24")

    assert row["method"] == "monthly_ended"
    assert row["end_estimate"] == pd.Timestamp("2025-04-05")


def test_monthly_orders_still_arriving_are_active(make_orders):
    months = ["2026-07-05", "2026-08-05", "2026-09-05", "2026-10-05"]
    df = make_orders([{"Codigo": f"A-{i}", "FechaEnvio": d} for i, d in enumerate(months)])
    row = contract(build_contracts(df), "100-1-LR24")

    assert row["method"] == "monthly_active"
    assert pd.isna(row["end_estimate"])


def test_urgency_signals_count_only_recent_months(make_orders):
    df = make_orders([
        {"Codigo": "A-1", "FechaEnvio": "2026-09-01", "ProcedenciaOC": "Emergencia, urgencia o imprevisto"},
        {"Codigo": "A-2", "FechaEnvio": "2026-10-01",
         "ProcedenciaOC": "Prórroga de un contrato de suministro o servicio"},
        {"Codigo": "A-3", "FechaEnvio": "2025-01-01", "ProcedenciaOC": "Emergencia, urgencia o imprevisto"},
    ])
    signals = urgency_signals(df).loc["MUNICIPALIDAD DE PRUEBA"]

    assert signals["emergency"] == 1  # the 2025 emergency is too old
    assert signals["extension"] == 1


def test_ai_durations_are_used_only_when_valid(make_orders, tmp_path, monkeypatch):
    df = make_orders([
        {"Codigo": "A-1", "FechaEnvio": "2025-01-10", "CodigoLicitacion": "1-1-LR25"},
        {"Codigo": "B-1", "FechaEnvio": "2025-01-10", "CodigoLicitacion": "2-1-LR25"},
        {"Codigo": "C-1", "FechaEnvio": "2025-01-10", "CodigoLicitacion": "3-1-LR25"},
        LAST_MONTH,
    ])
    answers = [
        {"contract_id": "1-1-LR25", "ai_months": 24, "ai_evidence": "por 24 meses"},  # valid
        {"contract_id": "2-1-LR25", "ai_months": 60, "ai_evidence": "2-1-LR25"},      # no time hint
        {"contract_id": "3-1-LR25", "ai_months": 1, "ai_evidence": "mes de enero"},   # one month
    ]
    ai_file = tmp_path / "ai_durations.jsonl"
    ai_file.write_text(
        "\n".join(json.dumps({"OrganismoPublico": "MUNICIPALIDAD DE PRUEBA", **a}) for a in answers),
        encoding="utf-8",
    )
    monkeypatch.setattr(estimate_contracts, "AI_FILE", ai_file)

    contracts = build_contracts(df)

    assert contract(contracts, "1-1-LR25")["method"] == "ai_text"
    assert contract(contracts, "1-1-LR25")["end_estimate"] == pd.Timestamp("2027-01-10")
    assert contract(contracts, "2-1-LR25")["method"] == "unknown"
    assert contract(contracts, "3-1-LR25")["method"] == "unknown"
