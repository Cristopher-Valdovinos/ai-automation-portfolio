import pandas as pd
import pytest

from weekly_report import HIDDEN_SUPPLIER, display_supplier, find_prospects, to_markdown

REPORT_DATE = pd.Timestamp("2026-11-17")


def make_contracts(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "OrganismoPublico": "MUNICIPALIDAD A", "service": "Servicios de limpieza",
        "region": "Región Metropolitana de Santiago", "supplier": "ASEO SPA",
        "start": pd.Timestamp("2024-11-01"), "total_amount": 500_000_000,
        "method": "unit_months", "emergency": 0, "extension": 0,
    }
    df = pd.DataFrame([{**defaults, **row} for row in rows])
    df["end_estimate"] = pd.to_datetime(df["end_estimate"])
    return df


def test_filters_window_amount_and_renewals():
    contracts = make_contracts([
        {"contract_id": "ok", "end_estimate": "2026-11-27"},
        {"contract_id": "too-far", "end_estimate": "2027-06-01"},
        {"contract_id": "too-small", "end_estimate": "2026-11-27", "total_amount": 10_000_000},
        {"contract_id": "renewed", "OrganismoPublico": "MUNICIPALIDAD B", "end_estimate": "2026-12-01"},
        {"contract_id": "new", "OrganismoPublico": "MUNICIPALIDAD B", "start": pd.Timestamp("2026-11-01"),
         "end_estimate": "2028-11-01"},
    ])
    prospects = find_prospects(contracts, REPORT_DATE)

    assert list(prospects["contract_id"]) == ["ok"]


def test_score_rewards_urgency_and_closeness():
    contracts = make_contracts([
        {"contract_id": "calm-far", "end_estimate": "2027-02-01"},
        {"contract_id": "urgent-near", "OrganismoPublico": "MUNICIPALIDAD C",
         "end_estimate": "2026-11-20", "emergency": 2},
    ])
    prospects = find_prospects(contracts, REPORT_DATE)

    assert list(prospects["contract_id"]) == ["urgent-near", "calm-far"]
    assert prospects["score"].between(0, 100).all()


def test_status_and_confidence_labels():
    contracts = make_contracts([
        {"contract_id": "past", "end_estimate": "2026-11-07", "method": "ai_text"},
        {"contract_id": "future", "OrganismoPublico": "MUNICIPALIDAD C", "end_estimate": "2026-11-27"},
    ])
    prospects = find_prospects(contracts, REPORT_DATE).set_index("contract_id")

    assert prospects.loc["past", "status"] == "venció hace 10 días, sin renovación visible"
    assert prospects.loc["past", "confidence"] == "media"
    assert prospects.loc["future", "status"] == "vence en 10 días"
    assert prospects.loc["future", "confidence"] == "alta"


@pytest.mark.parametrize("name, shown", [
    ("LIMCHILE S A", True),
    ("Dimension S.A.", True),
    ("Promarco SpA", True),
    ("Preserva Ltda", True),
    ("SOC DE INVERSIONES BIO REC LIMITADA", True),
    ("ProMarco y Cia Ltda", True),
    ("Yasna ", False),          # looks like a person's first name
    ("colala", False),
    ("Sasa Servicios", False),  # "Sa" inside a word is not "S.A."
])
def test_display_supplier_hides_names_without_company_form(name, shown):
    expected = name.strip() if shown else HIDDEN_SUPPLIER
    assert display_supplier(name) == expected


def test_markdown_lists_prospects():
    contracts = make_contracts([{"contract_id": "ok", "end_estimate": "2026-11-27"}])
    markdown = to_markdown(find_prospects(contracts, REPORT_DATE), REPORT_DATE)

    assert markdown.startswith("# Radar de compradores públicos — 17-11-2026")
    assert "Prospectos: **1**" in markdown
    assert "| 1 |" in markdown and "MUNICIPALIDAD A" in markdown
