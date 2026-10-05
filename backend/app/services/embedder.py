"""384-dimensional sentence embedding service.

Wraps ``sentence-transformers`` ``all-MiniLM-L6-v2`` with lazy, thread-safe
model loading so that importing the service layer (CLI diagnostics, tests,
editors) never pays the ~90 MB model download cost.
"""
import logging
import threading

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

_model = None
_model_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    """Return the shared embedding model, loading it on first use."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info("Loading embedding model '%s'...", MODEL_NAME)
                _model = SentenceTransformer(MODEL_NAME)
                logger.info(
                    "Embedding model ready (dimensions=%s).", get_model_dimensions()
                )
    return _model


def get_model_dimensions() -> int:
    """Return the dimensionality of the loaded model."""
    model = get_model()
    if hasattr(model, "get_embedding_dimension"):
        return int(model.get_embedding_dimension())
    return int(model.get_sentence_embedding_dimension())


def get_embedding(text: str) -> list:
    """Encode ``text`` into a 384-dim Python float list for Neo4j vector search."""
    if not text or not str(text).strip():
        raise ValueError("Cannot embed empty text.")
    return get_model().encode(str(text)).tolist()
