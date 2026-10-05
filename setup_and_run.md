# NexusNote — Setup and Run

## 1. Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Neo4j instance with vector-index support (AuraDB Free or local)
- Ollama running at `http://localhost:11434` with `llama3.2:1b` pulled
- Optional for image OCR: Tesseract (`pytesseract` + `Pillow` are already in `backend/requirements.txt`)

Verify:

```powershell
python --version
node --version
npm --version
ollama list
```

## 2. Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Linux/macOS:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Configure `backend/.env`

Create `backend/.env`:

```dotenv
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=your-user
NEO4J_PASSWORD=your-password
OLLAMA_MODEL=llama3.2:1b
OLLAMA_HOST=http://localhost:11434
```

Optional overrides used by `backend/app/services/engine.py`:

```dotenv
MATCH_THRESHOLD=0.82
LLM_TIMEOUT_SECONDS=90
```

## 4. Start Ollama

```powershell
ollama pull llama3.2:1b
ollama serve
```

Check:

```powershell
Invoke-WebRequest http://localhost:11434/api/tags
```

## 5. Run backend

From `backend/`:

```powershell
uvicorn app.main:app --reload --port 8000
```

Expected:

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/api/health`

On startup the app creates the `factVectors` vector index and uniqueness constraints. If Neo4j is down, startup still succeeds but graph calls return errors until connectivity is restored.

## 6. Run frontend

Second terminal, from repo root:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

Vite proxies `/api` and `/static` to `http://localhost:8000` per `frontend/vite.config.js`. CORS is already enabled for `http://localhost:5173` in `backend/app/main.py`.

Optional backend-origin override:

```powershell
$env:VITE_BACKEND_ORIGIN="http://localhost:8000"
npm run dev
```

Production build:

```powershell
npm run build
npm run preview
```

## 7. Smoke test

1. Open `http://localhost:8000/api/health`.
   - Expect `"api": "ok"`, `"neo4j": "connected"`, `"ollama": "connected"`.
2. Open `http://localhost:5173`.
3. Click Upload, send a `.pdf`, `.txt`, or image.
4. Confirm new concept nodes appear.
5. Click a node, open Facts & Sources and Visual Artifacts tabs.
6. Upload endpoint direct test:

```powershell
curl.exe -X POST http://localhost:8000/api/documents/upload -F "file=@C:\path\to\lecture.pdf"
```

## 8. Troubleshooting

- Backend unreachable: ensure `uvicorn app.main:app --reload --port 8000` is running from `backend/`.
- Neo4j DNS/auth failure: verify `NEO4J_URI`, user/password, database status, and outbound Bolt/TLS access.
- Ollama failure: verify `ollama serve`, `ollama list`, and `OLLAMA_HOST`. Uploads fall back safely when Ollama JSON is unavailable.
- No text from PDF: scanned PDFs without a text layer return HTTP 422; upload the page image for OCR instead.
- No artifacts: images under `150x150` px or with aspect ratio outside `0.1–10` are intentionally ignored.
- Slow first upload: `all-MiniLM-L6-v2` downloads/loads lazily on first embedding call.
- Tesseract missing: only affects standalone image OCR, not normal PDF text extraction.

## 9. Useful commands

```powershell
python -m py_compile backend/app/main.py backend/app/services/parser.py backend/app/services/embedder.py backend/app/services/engine.py
npm run build --prefix frontend
```

```powershell
cd backend
python -m app.services.test_services
```
