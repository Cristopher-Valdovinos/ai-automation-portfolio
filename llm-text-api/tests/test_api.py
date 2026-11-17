"""Pruebas de la API con un Ollama simulado (no requieren GPU ni modelo)."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_ollama
from app.ollama_client import OllamaClient

MODELO = "modelo-prueba"


def cliente_con(handler) -> TestClient:
    """Crea un TestClient cuya dependencia de Ollama usa el handler simulado."""
    ollama = OllamaClient(
        base_url="http://ollama.test",
        model=MODELO,
        transport=httpx.MockTransport(handler),
        retry_delay=0,
    )
    app.dependency_overrides[get_ollama] = lambda: ollama
    return TestClient(app)


@pytest.fixture(autouse=True)
def limpiar_overrides():
    yield
    app.dependency_overrides.clear()


def respuesta_chat(contenido: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": contenido}})


def test_health_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": f"{MODELO}:latest"}]})

    r = cliente_con(handler).get("/health")
    assert r.status_code == 200
    assert r.json() == {
        "estado": "ok",
        "ollama_conectado": True,
        "modelo": MODELO,
        "modelo_disponible": True,
    }


def test_health_sin_ollama():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    r = cliente_con(handler).get("/health")
    assert r.status_code == 200
    assert r.json()["estado"] == "degradado"
    assert r.json()["ollama_conectado"] is False


def test_resumir():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == MODELO
        assert payload["stream"] is False
        assert "2 oraciones" in payload["messages"][0]["content"]
        assert payload["messages"][1]["content"] == "Un texto largo."
        return respuesta_chat("  Un resumen.  ")

    r = cliente_con(handler).post(
        "/resumir", json={"texto": "Un texto largo.", "max_oraciones": 2}
    )
    assert r.status_code == 200
    assert r.json() == {"resumen": "Un resumen.", "modelo": MODELO}


def test_resumir_valida_entrada():
    client = cliente_con(lambda request: respuesta_chat("x"))
    assert client.post("/resumir", json={"texto": ""}).status_code == 422
    assert (
        client.post("/resumir", json={"texto": "hola", "max_oraciones": 0}).status_code
        == 422
    )


def test_clasificar():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        enum = payload["format"]["properties"]["categoria"]["enum"]
        assert enum == ["reclamo", "consulta"]
        return respuesta_chat(
            json.dumps({"categoria": "reclamo", "justificacion": "Expresa molestia."})
        )

    r = cliente_con(handler).post(
        "/clasificar",
        json={"texto": "El pedido llegó roto.", "categorias": ["reclamo", " consulta ", "reclamo"]},
    )
    assert r.status_code == 200
    assert r.json()["categoria"] == "reclamo"
    assert r.json()["justificacion"] == "Expresa molestia."


def test_clasificar_categoria_fuera_de_lista():
    handler = lambda request: respuesta_chat(
        json.dumps({"categoria": "otra", "justificacion": "x"})
    )
    r = cliente_con(handler).post(
        "/clasificar", json={"texto": "hola", "categorias": ["a", "b"]}
    )
    assert r.status_code == 502


def test_clasificar_exige_dos_categorias_distintas():
    client = cliente_con(lambda request: respuesta_chat("{}"))
    r = client.post("/clasificar", json={"texto": "hola", "categorias": ["a", "a"]})
    assert r.status_code == 422


def test_extraer():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["format"]["required"] == ["nombre", "fecha"]
        return respuesta_chat(json.dumps({"nombre": "Ana Rojas", "fecha": None}))

    r = cliente_con(handler).post(
        "/extraer",
        json={"texto": "Hola, soy Ana Rojas.", "campos": ["nombre", "fecha"]},
    )
    assert r.status_code == 200
    assert r.json()["datos"] == {"nombre": "Ana Rojas", "fecha": None}


def test_json_invalido_devuelve_502():
    r = cliente_con(lambda request: respuesta_chat("no soy json")).post(
        "/extraer", json={"texto": "hola", "campos": ["nombre"]}
    )
    assert r.status_code == 502


def test_ollama_caido_devuelve_503():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    r = cliente_con(handler).post("/resumir", json={"texto": "hola"})
    assert r.status_code == 503
    assert "Ollama" in r.json()["detail"]


def test_timeout_devuelve_504():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    r = cliente_con(handler).post("/resumir", json={"texto": "hola"})
    assert r.status_code == 504


def test_modelo_no_encontrado_devuelve_502():
    handler = lambda request: httpx.Response(404, json={"error": "model not found"})
    r = cliente_con(handler).post("/resumir", json={"texto": "hola"})
    assert r.status_code == 502
    assert MODELO in r.json()["detail"]


def test_health_modelo_no_descargado():
    handler = lambda request: httpx.Response(200, json={"models": [{"name": "otro:latest"}]})
    r = cliente_con(handler).get("/health")
    assert r.json()["estado"] == "degradado"
    assert r.json()["ollama_conectado"] is True
    assert r.json()["modelo_disponible"] is False


def test_respuesta_vacia_devuelve_502():
    r = cliente_con(lambda request: respuesta_chat("   ")).post(
        "/resumir", json={"texto": "hola"}
    )
    assert r.status_code == 502


def test_reintenta_si_ollama_falla_una_vez():
    llamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        if len(llamadas) == 1:
            return httpx.Response(500, json={"error": "el modelo se cayó al cargar"})
        return respuesta_chat("Un resumen.")

    r = cliente_con(handler).post("/resumir", json={"texto": "hola"})
    assert r.status_code == 200
    assert r.json()["resumen"] == "Un resumen."
    assert len(llamadas) == 2


def test_error_persistente_devuelve_502_tras_reintentar():
    llamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        return httpx.Response(500, json={"error": "fallo"})

    r = cliente_con(handler).post("/resumir", json={"texto": "hola"})
    assert r.status_code == 502
    assert len(llamadas) == 2
