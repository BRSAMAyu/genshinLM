# User Guide

## Start

```powershell
uvicorn app_service.main:app --host 127.0.0.1 --port 8765
cd desktop
npm run dev
```

Open `http://127.0.0.1:5173`.

## Calibration

Use the Calibration page to select a window, preview a screenshot, draw ROIs, check model status, and save an active profile.

## Skill Recorder

Open Skill Library:

1. Click `Start Recording`.
2. Perform the authorized dry-run or sandbox action.
3. Click `Stop Recording`.
4. Review segments and suggestions.
5. Save, validate, and dry-run the Skill.

## Planner

Open Task Planner, enter a natural language goal, and generate a mock TaskSpec. The TaskSpec must pass sandbox validation before any run.

## Companion

Open Companion and trigger mock events such as `TARGET_LOST` or `DODGE_REFLEX` to preview user-facing explanations.

## Combat Demo

Open Combat, generate a playbook, then trigger danger. The panel shows DangerScore, P1 interrupt details, and the dodge intent.
