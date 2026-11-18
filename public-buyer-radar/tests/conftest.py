"""Shared helpers: build small fake order tables for the tests."""

import pandas as pd
import pytest

import estimate_contracts
from estimate_contracts import prepare_orders


@pytest.fixture(autouse=True)
def no_real_ai_file(tmp_path, monkeypatch):
    """Tests never read the real AI answers in data/ (it may not exist in CI)."""
    monkeypatch.setattr(estimate_contracts, "AI_FILE", tmp_path / "missing.jsonl")

DEFAULT_ORDER = {
    "Nombre": "Servicio de aseo",
    "Descripcion/Obervaciones": "",
    "ProcedenciaOC": "Proveniente de licitación pública",
    "MontoTotalOC_PesosChilenos": "1000000",
    "OrganismoPublico": "MUNICIPALIDAD DE PRUEBA",
    "sector": "Municipalidades",
    "RegionUnidadCompra": "Región Metropolitana de Santiago",
    "NombreProveedor": "ASEO SPA",
    "CodigoLicitacion": "100-1-LR24",
    "RubroN2": "Servicios de limpieza",
    "RubroN3": "Servicios de limpieza de edificios",
    "cantidad": "1",
    "UnidadMedida": "Unidad",
}


@pytest.fixture
def make_orders():
    """Return a function that builds prepared orders from a few fields per row.

    Each row needs at least "Codigo" and "FechaEnvio"; the rest use defaults.
    """
    def build(rows: list[dict]) -> pd.DataFrame:
        raw = pd.DataFrame([{**DEFAULT_ORDER, **row} for row in rows])
        return prepare_orders(raw)

    return build
