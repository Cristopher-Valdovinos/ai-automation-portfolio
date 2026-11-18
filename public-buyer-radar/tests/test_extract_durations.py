import io
import json

import pytest

import extract_durations
from extract_durations import MAX_TEXT, ask_model, clean_answer, contract_text

TEXT = "Servicio de aseo integral por 24 meses. Licitación 757-28-LR25"


@pytest.mark.parametrize("answer, expected", [
    ({"duracion_meses": 24, "evidencia": "por 24 meses"}, (24, "por 24 meses")),
    ({"duracion_meses": 24, "evidencia": "POR 24 MESES"}, (24, "POR 24 MESES")),  # case does not matter
    ({"duracion_meses": 24, "evidencia": "por 36 meses"}, (None, None)),          # not in the text
    ({"duracion_meses": 60, "evidencia": "757-28-LR25"}, (None, None)),           # not about time
    ({"duracion_meses": 0, "evidencia": "por 24 meses"}, (None, None)),           # out of range
    ({"duracion_meses": 500, "evidencia": "por 24 meses"}, (None, None)),         # out of range
    ({"duracion_meses": "24", "evidencia": "por 24 meses"}, (None, None)),        # not an integer
    ({"duracion_meses": None, "evidencia": None}, (None, None)),                  # model said "unknown"
])
def test_clean_answer(answer, expected):
    assert clean_answer(answer, TEXT) == expected


def test_contract_text_joins_fields_and_skips_empty(make_orders):
    items = make_orders([{
        "Codigo": "A-1", "FechaEnvio": "2025-01-10", "Nombre": "Aseo 2026-2028",
        "Descripcion/Obervaciones": None, "cantidad": "36", "UnidadMedida": "Mes",
    }])
    text = contract_text(items)

    assert text.splitlines()[0] == "Aseo 2026-2028"
    assert "nan" not in text
    assert text.endswith("cantidad 36 Mes")


def test_contract_text_is_truncated(make_orders):
    items = make_orders([{"Codigo": "A-1", "FechaEnvio": "2025-01-10", "Nombre": "x" * 5000}])
    assert len(contract_text(items)) == MAX_TEXT


def test_ask_model_sends_expected_request(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["body"] = json.loads(request.data)
        reply = {"response": json.dumps({"duracion_meses": 12, "evidencia": "12 meses"})}
        return io.BytesIO(json.dumps(reply).encode())

    monkeypatch.setattr(extract_durations.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(extract_durations, "NUM_GPU", "")

    answer = ask_model("texto")

    assert answer == {"duracion_meses": 12, "evidencia": "12 meses"}
    assert sent["url"].endswith("/api/generate")
    assert sent["body"]["format"] == "json"
    assert sent["body"]["system"] == extract_durations.SYSTEM
    assert sent["body"]["options"] == {"temperature": 0}  # no num_gpu: Ollama decides


def test_ask_model_can_force_cpu(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["body"] = json.loads(request.data)
        return io.BytesIO(json.dumps({"response": "{}"}).encode())

    monkeypatch.setattr(extract_durations.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(extract_durations, "NUM_GPU", "0")

    ask_model("texto")

    assert sent["body"]["options"]["num_gpu"] == 0
