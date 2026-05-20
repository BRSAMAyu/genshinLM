# Install

## Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_windows.ps1
```

Manual equivalent:

```powershell
python -m pip install -r requirements.txt
cd desktop
npm install
npm run build
```

Run `python scripts/doctor.py` after installation.

