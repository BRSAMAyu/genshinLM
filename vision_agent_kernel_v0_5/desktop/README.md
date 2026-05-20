# Desktop Shell

Start the local service first:

```powershell
uvicorn app_service.main:app --host 127.0.0.1 --port 8765
```

Run the web shell:

```powershell
cd desktop
npm install
npm run dev
```

If the Tauri toolchain is installed:

```powershell
cd desktop
npm run tauri dev
```

The shell talks only to the local FastAPI service. Default mode remains dry-run.
