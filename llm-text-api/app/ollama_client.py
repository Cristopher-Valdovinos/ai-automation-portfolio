"""Cliente asíncrono mínimo para la API HTTP de Ollama."""

import asyncio
import json
from typing import Any

import httpx


class OllamaError(Exception):
    """Error al hablar con Ollama, con el código HTTP que la API debe devolver."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
        retries: int = 1,
        retry_delay: float = 2.0,
    ) -> None:
        self.model = model
        self._retries = retries
        self._retry_delay = retry_delay
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, transport=transport
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        for intento in range(self._retries + 1):
            try:
                response = await self._http.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                raise OllamaError(504, "Ollama tardó demasiado en responder.") from exc
            except httpx.TransportError as exc:
                raise OllamaError(503, "No se pudo conectar con Ollama.") from exc

            # Un error 5xx suele ser pasajero (por ejemplo, el modelo se cayó
            # mientras cargaba), así que se reintenta antes de rendirse.
            if response.status_code < 500 or intento == self._retries:
                break
            await asyncio.sleep(self._retry_delay)

        if response.status_code == 404:
            raise OllamaError(
                502, f"Ollama no encontró el modelo '{self.model}'. ¿Está descargado?"
            )
        if response.is_error:
            raise OllamaError(
                502, f"Ollama respondió con un error ({response.status_code})."
            )
        return response.json()

    async def list_models(self) -> list[str]:
        data = await self._request("GET", "/api/tags")
        return [m["name"] for m in data.get("models", [])]

    async def chat(
        self,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Envía un mensaje al modelo y devuelve el texto de la respuesta.

        Si se entrega `schema` (JSON Schema), Ollama restringe la salida a ese formato.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if schema is not None:
            payload["format"] = schema

        data = await self._request("POST", "/api/chat", json=payload)
        content = data.get("message", {}).get("content", "").strip()
        if not content:
            raise OllamaError(502, "El modelo devolvió una respuesta vacía.")
        return content

    async def chat_json(
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Igual que `chat`, pero exige y parsea una respuesta JSON."""
        content = await self.chat(system, user, schema=schema, temperature=0.0)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaError(502, "El modelo no devolvió un JSON válido.") from exc
        if not isinstance(parsed, dict):
            raise OllamaError(502, "El modelo no devolvió un objeto JSON.")
        return parsed
