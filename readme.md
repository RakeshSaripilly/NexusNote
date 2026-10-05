# NexusNote

NexusNote is a self-hosted GraphRAG knowledge synthesizer for study material. It turns PDFs, text files, and images into an interactive Neo4j knowledge graph with:

- Semantic fact deduplication using `all-MiniLM-L6-v2` embeddings.
- LLM-assisted merge decisions through Ollama.
- Page- and document-level source provenance.
- Embedded diagram and image extraction.
- React Flow graph exploration with Dagre auto-layout.
- Click-to-trace facts, source snippets, and visual artifacts.

## Features

### Document ingestion

Supported uploads:

- `.pdf`
- `.txt`
- `.md`
- `.png`
- `.jpg` / `.jpeg`
- `.webp`
- `.bmp`

PDF text is processed page-by-page. Text is normalized and split into sentence windows of three sentences with one sentence of overlap. Every chunk records its source file, location tag, page number, and raw snippet.

Images embedded in PDFs are extracted defensively. An image is saved only when:

- Width is at least 150 pixels.
- Height is at least 150 pixels.
- Aspect ratio is between `0.1` and `10`.

Extracted images are normalized to PNG and stored under `backend/static/artifacts/`. Small icons, bullets, and divider lines are ignored. Uploaded standalone images are OCR'd with Tesseract and are also registered as visual artifacts.

### Knowledge synthesis

Each extracted chunk is embedded into a 384-dimensional vector. Neo4j's native vector index finds the closest existing fact using cosine similarity.

- Score `>= 0.82`: Ollama decides whether to merge the source, extend an existing concept, or create a related subtopic.
- Score `< 0.82`: Ollama proposes a new concept and fact.
- Invalid, unavailable, or timed-out Ollama responses safely fall back to `EXTEND_NODE` for matched content.
- New-concept extraction also has a heuristic fallback, so uploads do not depend on perfectly formatted LLM output.

### Frontend exploration

The frontend provides:

- Dark React Flow graph canvas.
- Custom concept cards with fact and artifact counts.
- Dagre hierarchical layout (`TB`, `nodesep: 80`, `ranksep: 100`).
- Concept search and graph focusing.
- Drag-and-drop upload modal with progress and processing summary.
- Provenance drawer with fact/source and visual-artifact tabs.
- Expandable citation pills showing original snippets.
- Fullscreen artifact lightbox with keyboard navigation.

## Architecture

```text
NexusNote/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app and REST endpoints
│   │   ├── services/
│   │   │   ├── embedder.py            # Lazy SentenceTransformer service
│   │   │   ├── engine.py              # Neo4j + Ollama GraphRAG pipeline
│   │   │   ├── parser.py              # Text, PDF, OCR and artifact parsing
│   │   │   └── test_services.py       # Manual dependency health check
│   │   └── __init__.py
│   ├── static/
│   │   └── artifacts/                 # Runtime-generated PNG files
│   ├── requirements.txt
│   └── .env                           # Local secrets; do not commit
├── frontend/
│   ├── src/
│   │   ├── api/client.js              # Axios API client
│   │   ├── components/
│   │   │   ├── ArtifactLightbox.jsx
│   │   │   ├── CustomConceptNode.jsx
│   │   │   ├── ProvenanceDrawer.jsx
│   │   │   └── TopBar.jsx
│   │   ├── utils/layout.js             # Dagre positioning
│   │   ├── App.jsx
│   │   ├── index.css
│   │   └── main.jsx
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
└── README.md
```

## Requirements

- Python 3.11 or newer.
- Node.js 18 or newer and npm.
- Neo4j AuraDB Free or a local Neo4j instance with vector index support.
- Ollama installed and running locally.
- Tesseract OCR installed if standalone image OCR is required.

The embedding model is downloaded automatically on first use:

```text
sentence-transformers/all-MiniLM-L6-v2
```

The first embedding request can therefore take longer than subsequent requests.

## Backend setup

From the repository root:

### 1. Create and activate a virtual environment

Windows PowerShell:

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

### 2. Configure `backend/.env`

```dotenv
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b

# Optional tuning values
MATCH_THRESHOLD=0.82
LLM_TIMEOUT_SECONDS=90
```

Do not commit `.env`. It is ignored by Git.

### 3. Install and start Ollama

Install Ollama from [ollama.com](https://ollama.com), then pull the configured model:

```powershell
ollama pull llama3.2:1b
ollama serve
```

If Ollama is already running as a system service, only the `pull` command may be necessary.

### 4. Start FastAPI

Run from the `backend` directory so the `app` package is on the import path:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at:

- API base: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

At startup, NexusNote attempts to create:

- The `factVectors` native Neo4j vector index.
- Uniqueness constraints for concepts, facts, sources, and artifacts.

If Neo4j is temporarily unavailable, the API process still starts, but graph operations will fail until connectivity is restored.

## Frontend setup

Open a second terminal from the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

The Vite development server proxies `/api` and `/static` to `http://localhost:8000`. The frontend client defaults to the same backend origin, but it can be overridden:

PowerShell:

```powershell
$env:VITE_BACKEND_ORIGIN="http://localhost:8000"
npm run dev
```

For a production build:

```powershell
npm run build
npm run preview
```

## REST API

### `GET /api/health`

Checks API availability and reports Neo4j and Ollama status.

Example response:

```json
{
  "api": "ok",
  "neo4j": "connected",
  "ollama_model": "llama3.2:1b",
  "ollama": "connected"
}
```

### `POST /api/documents/upload`

Accepts a multipart upload with field name `file`.

Example with PowerShell:

```powershell
curl.exe -X POST http://localhost:8000/api/documents/upload `
  -F "file=@C:\path\to\lecture.pdf"
```

Example response:

```json
{
  "file_name": "lecture.pdf",
  "chunks_processed": 12,
  "artifacts_extracted": 3,
  "actions": {
    "created": 4,
    "extended": 5,
    "merged": 2,
    "spun_off": 1,
    "failed": 0
  },
  "concepts_touched": ["concept-uuid-1", "concept-uuid-2"],
  "failures": []
}
```

### `GET /api/graph`

Returns React Flow-compatible concept nodes and relationship edges.

```json
{
  "nodes": [
    {
      "id": "c1",
      "type": "customConceptNode",
      "data": {
        "label": "Virtual DOM",
        "factCount": 3,
        "artifactCount": 1
      }
    }
  ],
  "edges": [
    {
      "id": "e-c1-c2",
      "source": "c1",
      "target": "c2",
      "label": "relates_to",
      "animated": true
    }
  ]
}
```

### `GET /api/concept/{concept_id}`

Returns all facts, source citations, and visual artifacts associated with a concept.

```json
{
  "id": "c1",
  "title": "Virtual DOM",
  "facts": [
    {
      "fact_id": "f1",
      "text": "React batches DOM updates using reconciliation.",
      "sources": [
        {
          "file_name": "Lecture_1.pdf",
          "location_tag": "Page 3",
          "raw_snippet": "React batches DOM updates..."
        }
      ]
    }
  ],
  "artifacts": [
    {
      "id": "art-1",
      "image_url": "/static/artifacts/art-1.png",
      "file_name": "Lecture_1.pdf",
      "location_tag": "Page 3",
      "caption": "Diagram from Page 3"
    }
  ]
}
```

## Neo4j data model

### Nodes

| Label | Important properties |
|---|---|
| `Concept` | `id`, unique `title`, `created_at` |
| `Fact` | `id`, `text`, 384-dimensional `embedding`, `created_at` |
| `Source` | `id`, `file_name`, `location_tag`, `raw_snippet`, `uploaded_at` |
| `Artifact` | `id`, `file_name`, `location_tag`, `image_url`, `caption`, `created_at` |

### Relationships

```text
(:Concept)-[:HAS_FACT]->(:Fact)
(:Fact)-[:EXTRACTED_FROM]->(:Source)
(:Concept)-[:HAS_ARTIFACT]->(:Artifact)
(:Fact)-[:ILLUSTRATED_BY]->(:Artifact)
(:Concept)-[:RELATES_TO {type}]->(:Concept)
```

The vector index is named `factVectors` and uses cosine similarity over 384-dimensional fact embeddings.

## Processing flow

```text
Upload
  │
  ├─ PDF parser ── page text chunks + embedded image artifacts
  ├─ TXT parser ── text chunks
  └─ Image parser ── OCR chunks + uploaded image artifact
       │
       ▼
384-dim SentenceTransformer embedding
       │
       ▼
Neo4j factVectors query, threshold 0.82
       │
       ├─ Match: Ollama MERGE_SOURCE / EXTEND_NODE / SPIN_OFF_NODE
       └─ No match: Ollama new concept + fact extraction
       │
       ▼
Neo4j concept, fact, source, artifact and relationship writes
       │
       ▼
React Flow graph + provenance drawer
```

## Testing and validation

### Python syntax checks

From the repository root:

```powershell
python -m py_compile `
  backend/app/main.py `
  backend/app/services/parser.py `
  backend/app/services/embedder.py `
  backend/app/services/engine.py
```

### Frontend production build

```powershell
npm run build --prefix frontend
```

### Existing dependency health check

The repository contains `backend/app/services/test_services.py`, which checks:

1. Environment configuration.
2. Neo4j connectivity and vector index creation.
3. SentenceTransformer embedding dimensions.
4. Ollama JSON responses.
5. End-to-end ingestion and source lineage.

Run it from `backend`:

```powershell
python -m app.services.test_services
```

This check requires reachable Neo4j, Ollama, and the embedding model.

## Troubleshooting

### `Cannot reach the NexusNote backend`

Make sure FastAPI is running:

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

Then visit `http://localhost:8000/api/health`.

### Neo4j DNS or connection errors

Check:

- `NEO4J_URI` includes the correct AuraDB hostname.
- The database is running.
- Your network permits Bolt/Neo4j TLS traffic.
- The username and password are current.
- AuraDB IP/network restrictions are not blocking your machine.

### Ollama connection errors

Check the service and model:

```powershell
Invoke-WebRequest http://localhost:11434/api/tags
ollama list
ollama pull llama3.2:1b
```

The merge engine logs a safe fallback when a matched chunk cannot receive an Ollama decision.

### Tesseract is not installed

PDF text extraction does not require Tesseract. OCR for standalone image uploads does. Install Tesseract and ensure its executable is available on `PATH`, or configure `pytesseract.pytesseract.tesseract_cmd` for a custom installation path.

### No artifacts appear

The parser intentionally rejects images smaller than `150 × 150` pixels or with extreme aspect ratios. Some PDFs do not contain embedded raster images; diagrams rendered as vector drawing commands are not extracted by the current embedded-image path.

### The first upload is slow

The SentenceTransformer model is loaded lazily on the first embedding request. Later requests reuse the process-wide model instance.

### Uploaded PDF has no chunks

A PDF with only scanned pages may have no text layer. Use OCR preprocessing or upload the page image directly.

## Security and operational notes

- Keep `backend/.env` private.
- The API currently has no authentication; deploy it behind an authenticated reverse proxy before exposing it publicly.
- Artifact files are served directly from `/static/artifacts/`.
- Upload limits, antivirus scanning, rate limiting, and persistent object storage should be added for production deployments.
- The local artifact directory is intentionally ignored by Git.
- Neo4j and Ollama are external runtime dependencies; they are not bundled with the repository.

## Current limitations

- The graph is persisted in Neo4j, while extracted artifact PNGs are stored on the local filesystem.
- The parser extracts embedded raster images from PDFs, not vector-only diagrams.
- OCR quality depends on the local Tesseract installation and source image quality.
- There is no authentication or multi-user workspace isolation.
- Upload processing runs synchronously from the API request perspective, although blocking work is moved off the FastAPI event loop.
- Very large documents may benefit from a background job queue and progress persistence.

## License

No license has been specified for this repository yet. Add a project license before distributing NexusNote.