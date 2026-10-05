"""FastAPI application exposing the NexusNote ingestion and graph API."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.services import engine, parser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("nexusnote.api")

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"
ARTIFACT_DIR = STATIC_DIR / "artifacts"

# The mount target must exist before StaticFiles is instantiated.
parser.ensure_artifact_dir()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Artifact directory ready at %s", ARTIFACT_DIR)
    try:
        await run_in_threadpool(engine.init_schema)
        logger.info("Neo4j schema ready (vector index + uniqueness constraints).")
    except Exception as exc:
        logger.error("Neo4j schema initialisation failed: %s", exc)
    yield
    await run_in_threadpool(engine.close_driver)
    logger.info("Neo4j driver closed.")


app = FastAPI(
    title="NexusNote API",
    description="Interactive GraphRAG knowledge synthesizer with deep source lineage.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/health", tags=["system"])
@app.get("/health", include_in_schema=False)
async def health():
    """Report connectivity of every downstream dependency."""
    status = {"api": "ok", "neo4j": "unavailable", "ollama_model": engine.OLLAMA_MODEL}

    try:
        await run_in_threadpool(engine.get_driver().verify_connectivity)
        status["neo4j"] = "connected"
    except Exception as exc:
        status["neo4j"] = f"error: {exc}"

    try:
        await run_in_threadpool(engine.ollama_client.list)
        status["ollama"] = "connected"
    except Exception as exc:
        status["ollama"] = f"unavailable: {exc}"

    return status


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Ingest a PDF/TXT/image: extract text + artifacts, run the merge pipeline."""
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail=f"'{file.filename}' is empty.")

    try:
        chunks, artifacts = await run_in_threadpool(
            parser.parse_document, payload, file.filename
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to parse '%s'", file.filename)
        raise HTTPException(
            status_code=422, detail=f"Could not parse '{file.filename}': {exc}"
        ) from exc

    if not chunks:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No readable text found in '{file.filename}'. "
                "Scanned PDFs without a text layer need OCR preprocessing."
            ),
        )

    try:
        stats = await run_in_threadpool(engine.ingest_document, chunks, artifacts)
    except Exception as exc:
        logger.exception("Ingestion failed for '%s'", file.filename)
        raise HTTPException(status_code=502, detail=f"Graph write failed: {exc}") from exc

    actions = stats["actions"]
    logger.info(
        "Ingested %s: %d chunks, %d artifacts, %d concepts touched",
        file.filename,
        stats["chunks_processed"],
        len(artifacts),
        len(stats["concepts_touched"]),
    )

    return {
        "file_name": file.filename,
        "chunks_processed": stats["chunks_processed"],
        "artifacts_extracted": len(artifacts),
        "actions": {
            "created": actions.get("CREATE_NODE", 0),
            "extended": actions.get("EXTEND_NODE", 0),
            "merged": actions.get("MERGE_SOURCE", 0),
            "spun_off": actions.get("SPIN_OFF_NODE", 0),
            "failed": actions.get("failed", 0),
        },
        "concepts_touched": stats["concepts_touched"],
        "failures": stats["failures"],
    }


@app.get("/api/graph")
async def get_graph():
    """Return nodes and edges pre-formatted for the React Flow canvas."""
    try:
        return await run_in_threadpool(engine.fetch_full_graph)
    except Exception as exc:
        logger.exception("Graph fetch failed")
        raise HTTPException(status_code=502, detail=f"Could not load graph: {exc}") from exc


@app.get("/api/concept/{concept_id}")
async def get_concept(concept_id: str):
    """Return facts, citations and image artifacts for the provenance drawer."""
    try:
        lineage = await run_in_threadpool(engine.fetch_concept_lineage, concept_id)
    except Exception as exc:
        logger.exception("Concept fetch failed for %s", concept_id)
        raise HTTPException(
            status_code=502, detail=f"Could not load concept {concept_id}: {exc}"
        ) from exc

    if not lineage["title"] and not lineage["facts"]:
        raise HTTPException(status_code=404, detail=f"Concept '{concept_id}' not found.")

    return lineage