# Public Buyer Radar

Sistema de prospección comercial B2B con datos abiertos de compras públicas de Chile. Detecta qué organismos del Estado están por volver a contratar un servicio, a quién le compran hoy y cuánto gastan, para que un proveedor llegue antes de que se publique la licitación.

> ¿No eres del área técnica? Lee la [explicación en simple](GUIA.md): qué es, para qué sirve y cómo funciona, sin jerga.

La versión 1 se enfoca en **servicios de limpieza industrial** (aseo, recolección de residuos y descontaminación): 34 meses de datos, 64.787 órdenes de compra, 1.022 organismos y 6.024 proveedores.

## Qué hace

1. **Descarga** las órdenes de compra mensuales de ChileCompra (unos 800 MB por mes) y guarda solo la categoría elegida (unos 350 KB por mes).
2. **Agrupa** las órdenes en contratos (organismo + licitación o trato directo) y **estima cuándo vence** cada uno.
3. **Usa un modelo de lenguaje local** para leer la duración del contrato en el texto libre de la orden, cuando no viene en los campos estructurados.
4. **Genera un reporte semanal** con los prospectos ordenados por puntaje.

## Ejemplo de resultado

Reporte al 17-11-2026: 84 prospectos, que suman $48.796 millones en contratos por vencer.

| # | Puntaje | Organismo | Servicio | Proveedor actual | Monto contrato | Estado | Confianza |
|---|---|---|---|---|---|---|---|
| 1 | 92 | Universidad del Bío-Bío | Servicios de limpieza | colala | $1.859 M | vence en 18 días | alta |
| 2 | 86 | I. Municipalidad de Conchalí | Servicios de limpieza | Prestación de Servicios Integrales SpA | $686 M | venció hace 10 días, sin renovación visible | media |
| 3 | 84 | Corp. Administrativa del Poder Judicial | Servicios de limpieza | LIMCHILE S.A. | $3.981 M | vence en 44 días | alta |

## Cómo se estima el vencimiento

Se aplica la primera regla que funcione:

| Regla | Cuándo aplica | Contratos | % del monto |
|---|---|---|---|
| `unit_months` | El ítem se mide en meses: inicio + cantidad de meses | 3.586 | 34,3% |
| `monthly_active` | Llegan órdenes todos los meses y siguen llegando | 780 | 12,2% |
| `monthly_ended` | Llegaban órdenes mensuales y se cortaron hace más de 3 meses | 1.380 | 9,1% |
| `ai_text` | El modelo de lenguaje encontró la duración en el texto | 93 | 6,6% |
| `unknown` | Ninguna regla aplica | 23.691 | 37,8% |

La mayoría de los contratos `unknown` son compras puntuales y pequeñas: los contratos de hasta $100 millones suman solo el 6,3% del monto.

## El paso con IA

La IA se usa solo donde una regla no alcanza: leer texto libre. Se envían al modelo los contratos grandes (sobre $100 millones) sin fecha estimada, y debe responder:

```json
{"duracion_meses": 72, "evidencia": "... RESIDUOS SÓLIDOS DOMICILIARIOS ... POR 72 MESES"}
```

Para evitar respuestas inventadas:

- El modelo debe citar la frase exacta que respalda su respuesta. **Si la frase no aparece en el texto, la respuesta se descarta.**
- Si el texto no dice la duración, debe responder `null`.
- Las duraciones fuera de 1 a 120 meses se descartan.

En la prueba con los 300 contratos más grandes encontró la duración en 93. En el resto, la orden solo dice "ORDEN DE COMPRA DESDE [código]" y el modelo respondió `null` en vez de inventar.

## Puntaje de prospectos

Entran al reporte los contratos de más de $50 millones que vencen o vencieron dentro de ±90 días y que no muestran renovación: el mismo organismo no tiene un contrato más nuevo para el mismo servicio. Este filtro descartó 72 de 156 candidatos.

| Componente | Puntos |
|---|---|
| Tamaño del contrato (percentil entre los prospectos) | 50 |
| Cercanía del vencimiento | 30 |
| Compras de emergencia o prórrogas en los últimos 6 meses | 20 |

Una compra de emergencia o una prórroga suele indicar que el contrato anterior venció y que viene una licitación nueva.

## Requisitos

- Python 3.10 o superior (probado con 3.14)
- [Ollama](https://ollama.com) con un modelo descargado (solo para el paso con IA)

## Cómo ejecutarlo

```powershell
cd public-buyer-radar
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 1. Descargar y filtrar (unos 100 MB de descarga por mes)
python src/fetch_orders.py 2024-01 2026-10

# 2. Estimar contratos
python src/estimate_contracts.py

# 3. (Opcional) Leer duraciones con IA y volver a estimar
python src/extract_durations.py --limit 300
python src/estimate_contracts.py

# 4. Reporte
python src/weekly_report.py
```

Los resultados quedan en `data/` (excluida de git): `contracts.csv` y `reports/prospects_AAAA-MM-DD.csv` / `.md`.

## Configuración del paso con IA

| Variable | Por defecto | Descripción |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL de Ollama |
| `OLLAMA_MODEL` | `Qwen-Local:latest` | Nombre del modelo, como aparece en `ollama list` |
| `OLLAMA_NUM_GPU` | `0` | Capas en GPU. `0` usa solo la CPU (unos 8 segundos por contrato) |

## Estructura

```
public-buyer-radar/
├── src/
│   ├── fetch_orders.py        # descarga y filtro por categoría
│   ├── estimate_contracts.py  # contratos, vencimientos y señales de urgencia
│   ├── extract_durations.py   # duración desde texto libre con IA local
│   └── weekly_report.py       # ranking y reporte de prospectos
├── data/                      # datos y reportes (no se suben a git)
├── requirements.txt
├── README.md
└── GUIA.md
```

## Decisiones de diseño

- **Filtrar al descargar:** cada mes pesa unos 800 MB sin comprimir; se lee por partes de 200.000 filas y solo se guarda la categoría elegida. 34 meses ocupan 13 MB en disco.
- **Reglas primero, IA después:** las reglas cubren el 55,6% del monto sin costo. La IA se usa solo para 300 contratos grandes, no para 29.530.
- **Evidencia obligatoria:** una respuesta del modelo sin cita verificable no se usa.
- **Procesos que se pueden retomar:** la descarga salta los meses ya procesados y la IA guarda cada respuesta al instante.
- **Fechas como estimación:** cada prospecto indica el método y su nivel de confianza.

## Limitaciones

- Las fechas de vencimiento son estimaciones; conviene confirmarlas en la ficha de la licitación.
- Los datos de ChileCompra tienen un día de desfase. Un contrato "vencido sin renovación" puede haberse renovado en el mes que aún no se descarga.
- Las señales de urgencia se cuentan por organismo, no por contrato.
- Todavía no tiene pruebas automáticas ni Docker.

## Próximos pasos

- Consultar la API de Mercado Público para leer la duración desde la ficha de la licitación.
- Ejecución automática semanal con alerta por correo.
- Fichas de prospecto redactadas por la IA, con sugerencias de cómo acercarse.

## Fuente de datos

[Datos Abiertos ChileCompra](https://datos-abiertos.chilecompra.cl/descargas): descarga masiva de órdenes de compra.

## Autor

Cristopher Valdovinos · [GitHub](https://github.com/Cristopher-Valdovinos) · [LinkedIn](https://linkedin.com/in/cristopher-valdovinos)

## Licencia

MIT (ver [LICENSE](../LICENSE))
