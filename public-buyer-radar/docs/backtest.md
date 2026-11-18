# Backtest del radar

Se generó el reporte en 19 fechas pasadas (el día 1 de cada mes, de 2025-01-01 a 2026-07-01), usando solo los datos disponibles en cada fecha. Luego se revisó con los datos reales si cada organismo empezó un **contrato nuevo del mismo servicio** (de al menos $25 M) dentro de los 120 días siguientes.

## Resultado

| Métrica | Valor |
|---|---|
| Prospectos evaluados | 1.206 |
| **Precisión** (prospectos que contrataron de nuevo) | **55%** |
| **Precisión del top 25** | **56%** |
| Línea base (elegir al azar entre compradores con contratos grandes) | 31% |
| **Mejora sobre el azar** | **1,8x** (top 25: 1,8x) |
| Cobertura (contratos grandes nuevos que el reporte anticipó) | 13% |
| Error típico de fecha (mediana) | 34 días |

## Qué prospectos aciertan más

| Grupo | Valor | Precisión | Prospectos |
|---|---|---|---|
| Estado | por vencer | 61% | 895 |
| Estado | ya vencido | 38% | 311 |
| Señales de urgencia | no | 51% | 604 |
| Señales de urgencia | sí | 59% | 602 |
| Puntaje | menos de 50 | 54% | 592 |
| Puntaje | 50 a 69 | 54% | 398 |
| Puntaje | 70 o más | 60% | 216 |
| Origen de la fecha | campos de la orden | 56% | 847 |
| Origen de la fecha | leída por la IA | 52% | 359 |

## Por fecha

| Fecha | Prospectos | Aciertos | Precisión | Línea base |
|---|---|---|---|---|
| 2025-01-01 | 60 | 27 | 45% | 40% |
| 2025-02-01 | 65 | 23 | 35% | 37% |
| 2025-03-01 | 66 | 28 | 42% | 35% |
| 2025-04-01 | 68 | 42 | 62% | 35% |
| 2025-05-01 | 62 | 37 | 60% | 33% |
| 2025-06-01 | 62 | 38 | 61% | 31% |
| 2025-07-01 | 49 | 33 | 67% | 29% |
| 2025-08-01 | 42 | 25 | 60% | 28% |
| 2025-09-01 | 47 | 30 | 64% | 29% |
| 2025-10-01 | 57 | 31 | 54% | 33% |
| 2025-11-01 | 75 | 40 | 53% | 34% |
| 2025-12-01 | 67 | 36 | 54% | 34% |
| 2026-01-01 | 72 | 43 | 60% | 34% |
| 2026-02-01 | 74 | 43 | 58% | 32% |
| 2026-03-01 | 75 | 46 | 61% | 30% |
| 2026-04-01 | 69 | 36 | 52% | 28% |
| 2026-05-01 | 65 | 31 | 48% | 27% |
| 2026-06-01 | 67 | 38 | 57% | 25% |
| 2026-07-01 | 64 | 36 | 56% | 24% |

## Cómo leerlo

- Un **acierto** significa que el organismo volvió a contratar el servicio en el plazo; no dice qué proveedor ganó.
- La **línea base** responde: si un vendedor eligiera al azar entre todos los organismos que tienen contratos grandes de ese servicio, ¿cuántos contratarían en el mismo plazo?
- Un mismo contrato puede aparecer en varias fechas seguidas (el reporte mira ±90 días), así que las fechas no son independientes.
- Las duraciones leídas por la IA vienen del texto de cada orden, que existía desde su creación: no usan información del futuro.
