import pandas as pd

import run_weekly


def test_months_to_refresh_crosses_year():
    assert run_weekly.months_to_refresh(pd.Timestamp("2026-01-12")) == {(2025, 12), (2026, 1)}


def test_update_data_refreshes_only_recent_months(monkeypatch):
    calls = []
    monkeypatch.setattr(run_weekly, "HISTORY_START", "2026-08")
    monkeypatch.setattr(run_weekly.fetch_orders, "process_month",
                        lambda year, month, refresh=False: calls.append((year, month, refresh)))

    run_weekly.update_data(pd.Timestamp("2026-11-17"))

    assert calls == [(2026, 8, False), (2026, 9, False), (2026, 10, True), (2026, 11, True)]


def test_run_skips_llm_when_ollama_is_down(monkeypatch, capsys):
    steps = []
    monkeypatch.setattr(run_weekly, "update_data", lambda today: steps.append("data"))
    monkeypatch.setattr(run_weekly.estimate_contracts, "main", lambda: steps.append("estimate"))
    monkeypatch.setattr(run_weekly.extract_durations, "ollama_available", lambda: False)
    monkeypatch.setattr(run_weekly.extract_durations, "run", lambda: steps.append("llm"))
    monkeypatch.setattr(run_weekly.weekly_report, "run", lambda today: steps.append("report") or "report.md")

    run_weekly.run(pd.Timestamp("2026-11-17"))

    assert steps == ["data", "estimate", "report"]
    assert "Ollama is not running" in capsys.readouterr().out
