import pandas as pd
import pytest

from backtest import breakdown, evaluate_cutoff, new_contracts, summarize
from estimate_contracts import estimate

CUTOFF = pd.Timestamp("2026-01-01")
BIG = "100000000"


@pytest.fixture
def scenario(make_orders):
    """Three buyers with a large 12/36-month contract; only A renews after the cutoff."""
    return make_orders([
        # A: ends 2026-01-15 and signs a new contract on 2026-02-10 -> hit
        {"Codigo": "A-1", "FechaEnvio": "2025-01-15", "OrganismoPublico": "A", "CodigoLicitacion": "1-1-LR24",
         "cantidad": "12", "UnidadMedida": "Mes", "MontoTotalOC_PesosChilenos": BIG},
        {"Codigo": "A-2", "FechaEnvio": "2026-02-10", "OrganismoPublico": "A", "CodigoLicitacion": "2-1-LR26",
         "cantidad": "24", "UnidadMedida": "Mes", "MontoTotalOC_PesosChilenos": BIG},
        # B: ends 2026-01-20 and does not renew -> miss
        {"Codigo": "B-1", "FechaEnvio": "2025-01-20", "OrganismoPublico": "B", "CodigoLicitacion": "3-1-LR24",
         "cantidad": "12", "UnidadMedida": "Mes", "MontoTotalOC_PesosChilenos": BIG},
        # C: ends in 2027 -> not a prospect, but part of the baseline population
        {"Codigo": "C-1", "FechaEnvio": "2024-06-01", "OrganismoPublico": "C", "CodigoLicitacion": "4-1-LR24",
         "cantidad": "36", "UnidadMedida": "Mes", "MontoTotalOC_PesosChilenos": BIG},
    ])


def test_new_contracts_window(scenario):
    contracts = estimate(scenario)
    found = new_contracts(contracts, CUTOFF, days=60, min_amount=50_000_000)
    assert list(found["contract_id"]) == ["2-1-LR26"]
    assert new_contracts(contracts, CUTOFF, days=30, min_amount=50_000_000).empty


def test_evaluate_cutoff_uses_only_past_data(scenario):
    metrics, prospects = evaluate_cutoff(scenario, estimate(scenario), CUTOFF)

    # A is still a prospect: its new contract (after the cutoff) is not visible yet.
    assert set(prospects["OrganismoPublico"]) == {"A", "B"}
    assert prospects.set_index("OrganismoPublico")["hit"].to_dict() == {"A": True, "B": False}
    assert metrics["prospects"] == 2 and metrics["hits"] == 1
    assert metrics["population"] == 3 and metrics["population_hits"] == 1
    assert metrics["large_new"] == 1 and metrics["large_new_listed"] == 1
    assert metrics["timing_error_median"] == 26  # 2026-01-15 -> 2026-02-10


def test_summarize_and_breakdown(scenario):
    metrics, prospects = evaluate_cutoff(scenario, estimate(scenario), CUTOFF)
    summary = summarize(pd.DataFrame([metrics]))

    assert summary["precision"] == pytest.approx(0.5)
    assert summary["baseline"] == pytest.approx(1 / 3)
    assert summary["lift"] == pytest.approx(1.5)
    assert summary["coverage"] == pytest.approx(1.0)

    by_type = breakdown(prospects)
    assert set(by_type["group"]) == {"Estado", "Señales de urgencia", "Puntaje", "Origen de la fecha"}
    assert by_type["prospects"].groupby(by_type["group"]).sum().eq(2).all()
