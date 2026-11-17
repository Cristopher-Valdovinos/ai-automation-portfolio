"""API de procesamiento de texto con un modelo de lenguaje local (Ollama)."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.ollama_client import OllamaClient, OllamaError
from app.schemas import (
    ClasificarRequest,
    ClasificarResponse,
    ExtraerRequest,
    ExtraerResponse,
    HealthResponse,
    ResumirRequest,
    ResumirResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.ollama = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout=settings.ollama_timeout,
    )
    yield
    await app.state.ollama.close()


app = FastAPI(
    title="LLM Text API",
    description=(
        "Servicio REST para resumir, clasificar y extraer datos de texto "
        "usando un modelo de lenguaje local servido por Ollama."
    ),
    version=__version__,
    lifespan=lifespan,
)


def get_ollama(request: Request) -> OllamaClient:
    return request.app.state.ollama


Ollama = Annotated[OllamaClient, Depends(get_ollama)]


@app.exception_handler(OllamaError)
async def ollama_error_handler(_: Request, exc: OllamaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", response_model=HealthResponse, tags=["sistema"])
async def health(ollama: Ollama) -> HealthResponse:
    """Indica si la API está arriba y si Ollama y el modelo están disponibles."""
    try:
        modelos = await ollama.list_models()
    except OllamaError:
        return HealthResponse(
            estado="degradado",
            ollama_conectado=False,
            modelo=ollama.model,
            modelo_disponible=False,
        )
    disponible = ollama.model in modelos or f"{ollama.model}:latest" in modelos
    return HealthResponse(
        estado="ok" if disponible else "degradado",
        ollama_conectado=True,
        modelo=ollama.model,
        modelo_disponible=disponible,
    )


@app.post("/resumir", response_model=ResumirResponse, tags=["texto"])
async def resumir(body: ResumirRequest, ollama: Ollama) -> ResumirResponse:
    """Resume un texto en la cantidad máxima de oraciones indicada."""
    system = (
        "Eres un asistente que resume textos con precisión. "
        f"Responde solo con el resumen, en {body.idioma}, "
        f"en un máximo de {body.max_oraciones} oraciones. "
        "No agregues información que no esté en el texto."
    )
    resumen = await ollama.chat(system, body.texto)
    return ResumirResponse(resumen=resumen, modelo=ollama.model)


@app.post("/clasificar", response_model=ClasificarResponse, tags=["texto"])
async def clasificar(body: ClasificarRequest, ollama: Ollama) -> ClasificarResponse:
    """Asigna al texto una de las categorías entregadas."""
    schema = {
        "type": "object",
        "properties": {
            "categoria": {"type": "string", "enum": body.categorias},
            "justificacion": {"type": "string"},
        },
        "required": ["categoria", "justificacion"],
    }
    system = (
        "Clasifica el texto del usuario en exactamente una de estas categorías: "
        f"{', '.join(body.categorias)}. "
        "Responde en JSON con 'categoria' y una 'justificacion' de una oración."
    )
    data = await ollama.chat_json(system, body.texto, schema)

    categoria = data.get("categoria")
    if categoria not in body.categorias:
        raise OllamaError(502, "El modelo devolvió una categoría fuera de la lista.")
    return ClasificarResponse(
        categoria=categoria,
        justificacion=str(data.get("justificacion", "")).strip(),
        modelo=ollama.model,
    )


@app.post("/extraer", response_model=ExtraerResponse, tags=["texto"])
async def extraer(body: ExtraerRequest, ollama: Ollama) -> ExtraerResponse:
    """Extrae del texto los campos pedidos; devuelve null si un dato no aparece."""
    schema = {
        "type": "object",
        "properties": {campo: {"type": ["string", "null"]} for campo in body.campos},
        "required": body.campos,
    }
    system = (
        "Extrae del texto del usuario los siguientes datos: "
        f"{', '.join(body.campos)}. "
        "Responde en JSON con esas claves exactas. "
        "Si un dato no aparece en el texto, usa null. No inventes valores."
    )
    data = await ollama.chat_json(system, body.texto, schema)

    datos = {}
    for campo in body.campos:
        valor = data.get(campo)
        datos[campo] = None if valor is None else str(valor).strip() or None
    return ExtraerResponse(datos=datos, modelo=ollama.model)
