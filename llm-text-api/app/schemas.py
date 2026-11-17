"""Modelos de entrada y salida de la API."""

from pydantic import BaseModel, Field, field_validator

MAX_CARACTERES = 20_000

Texto = Field(
    min_length=1,
    max_length=MAX_CARACTERES,
    description="Texto a procesar.",
)


def _limpiar_lista(valores: list[str]) -> list[str]:
    """Quita espacios, vacíos y duplicados conservando el orden."""
    vistos: dict[str, None] = {}
    for valor in valores:
        valor = valor.strip()
        if valor:
            vistos.setdefault(valor, None)
    return list(vistos)


class ResumirRequest(BaseModel):
    texto: str = Texto
    max_oraciones: int = Field(default=3, ge=1, le=10)
    idioma: str = Field(default="español", min_length=2, max_length=30)


class ResumirResponse(BaseModel):
    resumen: str
    modelo: str


class ClasificarRequest(BaseModel):
    texto: str = Texto
    categorias: list[str] = Field(
        min_length=2, max_length=20, description="Categorías posibles."
    )

    @field_validator("categorias")
    @classmethod
    def validar_categorias(cls, valores: list[str]) -> list[str]:
        limpias = _limpiar_lista(valores)
        if len(limpias) < 2:
            raise ValueError("Se necesitan al menos 2 categorías distintas.")
        return limpias


class ClasificarResponse(BaseModel):
    categoria: str
    justificacion: str
    modelo: str


class ExtraerRequest(BaseModel):
    texto: str = Texto
    campos: list[str] = Field(
        min_length=1, max_length=20, description="Datos a extraer del texto."
    )

    @field_validator("campos")
    @classmethod
    def validar_campos(cls, valores: list[str]) -> list[str]:
        limpios = _limpiar_lista(valores)
        if not limpios:
            raise ValueError("Se necesita al menos 1 campo.")
        return limpios


class ExtraerResponse(BaseModel):
    datos: dict[str, str | None]
    modelo: str


class HealthResponse(BaseModel):
    estado: str
    ollama_conectado: bool
    modelo: str
    modelo_disponible: bool
