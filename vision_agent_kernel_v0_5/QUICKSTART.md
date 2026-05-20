# Quickstart

This project is dry-run-first. It is intended for authorized sandboxes, QA environments, and analysis workflows.

## 1. Diagnose

```powershell
python scripts/doctor.py
```

The report is written to `logs/doctor_report.json`.

## 2. Start Service And GUI

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_app.ps1
```

Service: `http://127.0.0.1:8765`
GUI: `http://127.0.0.1:5173`

## 3. Run Demo

```powershell
python scripts/validate_mvp.py
python scripts/run_showcase_demo.py --mode dry-run --seconds 30
```

## Safety

Real input is disabled by default. Safe-window mode is restricted to authorized test windows and still preserves emergency stop and `release_all`.

