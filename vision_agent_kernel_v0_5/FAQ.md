# FAQ

## The service does not start.

Run `python scripts/doctor.py` and check port `8765`. If busy, stop the old service or choose another port.

## The GUI is blank.

Run:

```powershell
cd desktop
npm install
npm run dev
```

## Can the LLM click buttons directly?

No. LLMs can only call whitelisted planning and explanation tools. They cannot call raw mouse or keyboard actions.

## Can I import community Skills?

Blueprint import is supported only after safety validation. Dangerous input, missing profiles, and unknown triggers are rejected.

