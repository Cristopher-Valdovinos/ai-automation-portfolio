"""Use a local LLM (Ollama) to read contract duration from order text.

Only large contracts whose end date the rules could not estimate are sent
to the model. Each answer is saved right away in a cache file, so the run
can be stopped and resumed without repeating work.

The model must quote the sentence that supports its answer ("evidencia"),
and must answer null when the text does not say. Answers without evidence
are discarded.

Usage:
    python src/extract_durations.py            # all pending contracts
    python src/extract_durations.py --limit 20 # quick test
"""

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

import pandas as pd

from estimate_contracts import load_orders  # same contract ID logic

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONTRACTS_FILE = DATA_DIR / "contracts.csv"
CACHE_FILE = DATA_DIR / "ai_durations.jsonl"

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "Qwen-Local:latest")
# 0 = run on CPU. Set OLLAMA_NUM_GPU to use the GPU if your drivers allow it.
NUM_GPU = int(os.getenv("OLLAMA_NUM_GPU", "0"))

MIN_AMOUNT = 100_000_000   # only contracts above 100 million CLP
MAX_MONTHS = 120
MAX_TEXT = 1500            # characters sent to the model

PROMPT = """Eres analista de compras públicas en Chile. Lee el texto de una orden de compra
y responde SOLO un JSON con:
- "duracion_meses": duración total del contrato en meses (número entero) o null si el texto no lo permite saber.
- "evidencia": la frase exacta del texto que lo respalda, o null.
No inventes. Si solo hay un periodo de fechas (ej. 2024-2029), calcula los meses.

Texto:
{text}"""


def contract_text(items: pd.DataFrame) -> str:
    """Join the useful text fields of a contract's first order."""
    first = items.sort_values("sent").iloc[0]
    parts = [
        first["Nombre"],
        first["Descripcion/Obervaciones"],
        *items["RubroN3"].dropna().unique()[:2],
        f"cantidad {first['cantidad']} {first['UnidadMedida']}",
    ]
    text = "\n".join(str(p) for p in parts if isinstance(p, str) and p.strip())
    return text[:MAX_TEXT]


def ask_model(text: str) -> dict:
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": PROMPT.format(text=text),
        "format": "json",
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_gpu": NUM_GPU},
    }).encode()
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", body, {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(json.loads(response.read())["response"])


def clean_answer(answer: dict, text: str) -> tuple[int | None, str | None]:
    """Keep the duration only if it is valid and the evidence is in the text."""
    months = answer.get("duracion_meses")
    evidence = answer.get("evidencia")
    if not isinstance(months, int) or not 1 <= months <= MAX_MONTHS:
        return None, None
    if not evidence or evidence.lower() not in text.lower():
        return None, None
    return months, evidence


def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    with CACHE_FILE.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    return {(r["OrganismoPublico"], r["contract_id"]): r for r in rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="process at most N contracts")
    args = parser.parse_args()

    contracts = pd.read_csv(CONTRACTS_FILE)
    pending = contracts[
        (contracts["method"] == "unknown") & (contracts["total_amount"] > MIN_AMOUNT)
    ].sort_values("total_amount", ascending=False)

    cache = load_cache()
    keys = list(zip(pending["OrganismoPublico"], pending["contract_id"]))
    todo = [k for k in keys if k not in cache]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(pending):,} large unknown contracts, {len(cache):,} cached, {len(todo):,} to process")
    if not todo:
        return

    items = load_orders()
    grouped = items.groupby(["OrganismoPublico", "contract_id"])

    with CACHE_FILE.open("a", encoding="utf-8") as cache_out:
        for i, key in enumerate(todo, start=1):
            text = contract_text(grouped.get_group(key))
            start = time.time()
            try:
                months, evidence = clean_answer(ask_model(text), text)
            except Exception as error:  # keep going; the contract stays pending
                print(f"[{i}/{len(todo)}] error: {error}")
                continue
            row = {"OrganismoPublico": key[0], "contract_id": key[1],
                   "ai_months": months, "ai_evidence": evidence}
            cache_out.write(json.dumps(row, ensure_ascii=False) + "\n")
            cache_out.flush()
            print(f"[{i}/{len(todo)}] {key[1]}: {months} months ({time.time() - start:.1f}s)")


if __name__ == "__main__":
    main()
