"""Neo4j Cypher transactions and Ollama merge logic."""

import json
import logging
import os
import re
import threading
import uuid
from collections import Counter
from pathlib import Path

import ollama
from dotenv import load_dotenv
from neo4j import GraphDatabase

from app.services.embedder import EMBEDDING_DIMENSIONS, get_embedding

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.82"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "90"))

VALID_ACTIONS = {"MERGE_SOURCE", "EXTEND_NODE", "SPIN_OFF_NODE"}

ollama_client = ollama.Client(host=OLLAMA_HOST, timeout=LLM_TIMEOUT_SECONDS)

_driver = None
_driver_lock = threading.Lock()


def get_driver():
    """Return the shared Neo4j driver, creating it on first use."""
    global _driver
    if _driver is None:
        with _driver_lock:
            if _driver is None:
                if not NEO4J_URI or not NEO4J_PASSWORD:
                    raise RuntimeError(
                        "Neo4j credentials missing. Set NEO4J_URI, NEO4J_USER and "
                        "NEO4J_PASSWORD in backend/.env"
                    )
                _driver = GraphDatabase.driver(
                    NEO4J_URI,
                    auth=(NEO4J_USER, NEO4J_PASSWORD),
                    max_connection_lifetime=30 * 60,
                    max_connection_pool_size=50,
                )
    return _driver


def close_driver():
    """Close the shared Neo4j driver if one was created."""
    global _driver
    with _driver_lock:
        if _driver is not None:
            _driver.close()
            _driver = None


# --------------------------------------------------------------------------- #
# Schema bootstrap
# --------------------------------------------------------------------------- #

VECTOR_INDEX_CYPHER = """
CREATE VECTOR INDEX factVectors IF NOT EXISTS
FOR (f:Fact) ON (f.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: $dimensions,
  `vector.similarity_function`: 'cosine'
}}
"""

CONSTRAINT_CYPHERS = [
    "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT concept_title IF NOT EXISTS FOR (c:Concept) REQUIRE c.title IS UNIQUE",
    "CREATE CONSTRAINT fact_id IF NOT EXISTS FOR (f:Fact) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT source_id IF NOT EXISTS FOR (s:Source) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT artifact_id IF NOT EXISTS FOR (a:Artifact) REQUIRE a.id IS UNIQUE",
]


def init_vector_index():
    """Create the 384-dim cosine vector index over :Fact nodes."""
    with get_driver().session() as session:
        session.run(VECTOR_INDEX_CYPHER, dimensions=EMBEDDING_DIMENSIONS)
    logger.info("Neo4j vector index 'factVectors' verified.")


def init_constraints():
    """Enforce the uniqueness guarantees the MERGE-based merge logic relies on."""
    with get_driver().session() as session:
        for cypher in CONSTRAINT_CYPHERS:
            session.run(cypher)
    logger.info("Neo4j uniqueness constraints verified.")


def init_schema():
    """Prepare the vector index and uniqueness constraints."""
    init_vector_index()
    init_constraints()


# --------------------------------------------------------------------------- #
# Vector search
# --------------------------------------------------------------------------- #

VECTOR_MATCH_CYPHER = """
CALL db.index.vector.queryNodes('factVectors', 1, $embedding)
YIELD node AS f, score
WHERE score >= $threshold
MATCH (c:Concept)-[:HAS_FACT]->(f)
RETURN c.id AS concept_id, c.title AS concept_title,
       f.id AS fact_id, f.text AS fact_text, score
LIMIT 1
"""


def query_vector_match(embedding, threshold=None):
    """Return the closest existing :Fact above ``threshold``, else ``None``."""
    threshold = MATCH_THRESHOLD if threshold is None else threshold
    with get_driver().session() as session:
        record = session.run(
            VECTOR_MATCH_CYPHER, embedding=embedding, threshold=threshold
        ).single()
    return dict(record) if record else None


# --------------------------------------------------------------------------- #
# Graph write Cypher
# --------------------------------------------------------------------------- #

CREATE_SOURCE_CYPHER = """
MATCH (f:Fact {id: $fact_id})
CREATE (s:Source {
  id: $source_id,
  file_name: $file_name,
  location_tag: $location_tag,
  raw_snippet: $raw_snippet,
  uploaded_at: datetime()
})
CREATE (f)-[:EXTRACTED_FROM]->(s)
"""

CREATE_FACT_SOURCE_CYPHER = """
MATCH (c:Concept {id: $concept_id})
CREATE (f:Fact {
  id: $fact_id,
  text: $fact_text,
  embedding: $embedding,
  created_at: datetime()
})
CREATE (s:Source {
  id: $source_id,
  file_name: $file_name,
  location_tag: $location_tag,
  raw_snippet: $raw_snippet,
  uploaded_at: datetime()
})
CREATE (c)-[:HAS_FACT]->(f)
CREATE (f)-[:EXTRACTED_FROM]->(s)
RETURN f.id AS fact_id
"""

CREATE_CONCEPT_CYPHER = """
MERGE (c:Concept {title: $concept_title})
  ON CREATE SET c.id = $concept_id, c.created_at = datetime()
CREATE (f:Fact {
  id: $fact_id,
  text: $fact_text,
  embedding: $embedding,
  created_at: datetime()
})
CREATE (s:Source {
  id: $source_id,
  file_name: $file_name,
  location_tag: $location_tag,
  raw_snippet: $raw_snippet,
  uploaded_at: datetime()
})
CREATE (c)-[:HAS_FACT]->(f)
CREATE (f)-[:EXTRACTED_FROM]->(s)
RETURN c.id AS concept_id
"""

SPIN_OFF_CYPHER = """
MATCH (parent:Concept {id: $parent_id})
MERGE (child:Concept {title: $new_concept})
  ON CREATE SET child.id = $concept_id, child.created_at = datetime()
CREATE (f:Fact {
  id: $fact_id,
  text: $fact_text,
  embedding: $embedding,
  created_at: datetime()
})
CREATE (s:Source {
  id: $source_id,
  file_name: $file_name,
  location_tag: $location_tag,
  raw_snippet: $raw_snippet,
  uploaded_at: datetime()
})
CREATE (child)-[:HAS_FACT]->(f)
CREATE (f)-[:EXTRACTED_FROM]->(s)
MERGE (child)-[:RELATES_TO {type: $relation}]->(parent)
RETURN child.id AS concept_id
"""

LINK_ARTIFACTS_CYPHER = """
MATCH (c:Concept {id: $concept_id})
UNWIND $artifacts AS item
MERGE (a:Artifact {id: item.id})
  ON CREATE SET a.file_name = item.file_name,
                a.location_tag = item.location_tag,
                a.image_url = item.image_url,
                a.caption = item.caption,
                a.created_at = datetime()
MERGE (c)-[:HAS_ARTIFACT]->(a)
"""

ILLUSTRATE_FACT_CYPHER = """
MATCH (f:Fact {id: $fact_id})
UNWIND $artifact_ids AS artifact_id
MATCH (a:Artifact {id: artifact_id})
MERGE (f)-[:ILLUSTRATED_BY]->(a)
"""


# --------------------------------------------------------------------------- #
# LLM helpers
# --------------------------------------------------------------------------- #

SYSTEM_DECISION_PROMPT = """You are a knowledge graph synthesizer.
Compare the NEW CHUNK with the EXISTING TOPIC and FACT.
Return ONLY valid JSON with one of these structures:

1. Duplicate information:
{"action": "MERGE_SOURCE"}

2. New bullet point under the same topic:
{"action": "EXTEND_NODE", "synthesized_fact": "concise bullet point"}

3. Distinct subtopic:
{"action": "SPIN_OFF_NODE", "new_concept": "Short Title", "relation": "relates_to", "synthesized_fact": "concise bullet point"}
"""


def _parse_json_object(raw):
    """Best-effort extraction of a JSON object from a raw LLM response."""
    if not raw:
        return None

    text = re.sub(r"^```(?:json)?", "", raw.strip()).strip()
    text = re.sub(r"```$", "", text).strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None

    return parsed if isinstance(parsed, dict) else None


def _chat_json(messages):
    """Call Ollama in forced-JSON mode and return the decoded object."""
    response = ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=messages,
        format="json",
        options={"temperature": 0.2},
    )
    content = ""
    if hasattr(response, "message") and hasattr(response.message, "content"):
        content = response.message.content
    elif isinstance(response, dict):
        content = response.get("message", {}).get("content", "")
    elif hasattr(response, "message") and isinstance(response.message, dict):
        content = response.message.get("content", "")
    return _parse_json_object(content)


def _trim(text, max_chars=320):
    """Shorten text into a concise bullet, preferring a sentence boundary."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    shortened = text[:max_chars]
    boundary = max(shortened.rfind(". "), shortened.rfind("! "), shortened.rfind("? "))
    return (shortened[: boundary + 1] if boundary > 60 else shortened).strip()


def _clean_title(title):
    """Normalise a concept title into a short, human-readable label."""
    if not title:
        return ""
    text = re.sub(r"\s+", " ", str(title)).strip()
    text = text.strip('"').strip("'").strip().rstrip(".:")
    return " ".join(text.split()[:5]).strip()


def _fallback_concept_title(text):
    """Derive a topic label without the LLM (used when Ollama is unavailable)."""
    words = re.findall(r"[A-Za-z0-9'\-]+", text or "")[:5]
    return " ".join(words).title() or "General Concept"


def _decide_merge_action(match, chunk):
    """Ask the LLM how a chunk relates to the best-scoring existing fact."""
    user_prompt = (
        f"EXISTING TOPIC: {match['concept_title']}\n"
        f"EXISTING FACT: {match['fact_text']}\n"
        f"NEW CHUNK: {chunk['text']}\n"
    )
    try:
        decision = _chat_json(
            [
                {"role": "system", "content": SYSTEM_DECISION_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
    except Exception as exc:
        logger.warning("Ollama merge decision failed (%s); defaulting to EXTEND_NODE.", exc)
        decision = None

    action = (decision or {}).get("action")
    if action not in VALID_ACTIONS:
        return {"action": "EXTEND_NODE", "synthesized_fact": _trim(chunk["text"])}

    return {**decision, "action": action}


def _extract_concept(chunk):
    """Ask the LLM for a new concept title and fact when no vector match exists."""
    prompt = (
        "Extract a short concept topic title (2-4 words) and a clean, concise "
        f"fact from this text: '{chunk['text']}'. "
        'Output JSON only: {"concept": "...", "fact": "..."}'
    )
    try:
        info = _chat_json([{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning("Ollama concept extraction failed (%s); using heuristics.", exc)
        info = None

    return {
        "concept": _clean_title((info or {}).get("concept"))
        or _fallback_concept_title(chunk["text"]),
        "fact": _trim((info or {}).get("fact") or chunk["text"]),
    }


def _source_params(chunk):
    """Build the :Source properties shared by every graph write path."""
    return {
        "file_name": chunk.get("file_name") or "Unknown Document",
        "location_tag": chunk.get("location_tag") or "Document",
        "raw_snippet": (chunk.get("raw_snippet") or chunk.get("text") or "")[:4000],
    }


def _artifact_params(artifacts):
    """Normalise artifact payloads for Cypher map projection."""
    return [
        {
            "id": artifact["id"],
            "file_name": artifact.get("file_name") or "Unknown Document",
            "location_tag": artifact.get("location_tag") or "Document",
            "image_url": artifact.get("image_url") or "",
            "caption": artifact.get("caption") or "Visual artifact",
        }
        for artifact in artifacts
    ]


def _attach_artifacts(session, concept_id, fact_id, artifacts):
    """Link a chunk's visual artifacts to the active concept and fact."""
    if not artifacts:
        return
    session.run(
        LINK_ARTIFACTS_CYPHER, concept_id=concept_id, artifacts=_artifact_params(artifacts)
    )
    session.run(
        ILLUSTRATE_FACT_CYPHER,
        fact_id=fact_id,
        artifact_ids=[artifact["id"] for artifact in artifacts],
    )


# --------------------------------------------------------------------------- #
# Ingestion pipeline
# --------------------------------------------------------------------------- #


def process_extracted_chunk(chunk, artifacts=None):
    """Route one chunk through vector match -> LLM decision -> graph writes."""
    artifacts = artifacts or []
    match = query_vector_match(get_embedding(chunk["text"]))

    with get_driver().session() as session:
        if match:
            decision = _decide_merge_action(match, chunk)
            action = decision["action"]

            if action == "MERGE_SOURCE":
                session.run(
                    CREATE_SOURCE_CYPHER,
                    fact_id=match["fact_id"],
                    source_id=str(uuid.uuid4()),
                    **_source_params(chunk),
                )
                concept_id, fact_id = match["concept_id"], match["fact_id"]

            elif action == "SPIN_OFF_NODE":
                fact_text = _trim(decision.get("synthesized_fact") or chunk["text"])
                fact_id = str(uuid.uuid4())
                record = session.run(
                    SPIN_OFF_CYPHER,
                    parent_id=match["concept_id"],
                    new_concept=_clean_title(decision.get("new_concept"))
                    or "Related Concept",
                    concept_id=str(uuid.uuid4()),
                    fact_id=fact_id,
                    fact_text=fact_text,
                    embedding=get_embedding(fact_text),
                    relation=(decision.get("relation") or "relates_to").strip().lower(),
                    source_id=str(uuid.uuid4()),
                    **_source_params(chunk),
                ).single()
                concept_id = record["concept_id"]

            else:  # EXTEND_NODE (also the safe default)
                fact_text = _trim(decision.get("synthesized_fact") or chunk["text"])
                fact_id = str(uuid.uuid4())
                session.run(
                    CREATE_FACT_SOURCE_CYPHER,
                    concept_id=match["concept_id"],
                    fact_id=fact_id,
                    fact_text=fact_text,
                    embedding=get_embedding(fact_text),
                    source_id=str(uuid.uuid4()),
                    **_source_params(chunk),
                )
                concept_id = match["concept_id"]

        else:
            extracted = _extract_concept(chunk)
            fact_id = str(uuid.uuid4())
            record = session.run(
                CREATE_CONCEPT_CYPHER,
                concept_title=extracted["concept"],
                concept_id=str(uuid.uuid4()),
                fact_id=fact_id,
                fact_text=extracted["fact"],
                embedding=get_embedding(extracted["fact"]),
                source_id=str(uuid.uuid4()),
                **_source_params(chunk),
            ).single()
            concept_id = record["concept_id"]
            action = "CREATE_NODE"

        _attach_artifacts(session, concept_id, fact_id, artifacts)

    return {
        "action": action,
        "concept_id": concept_id,
        "fact_id": fact_id,
        "match_score": match["score"] if match else None,
    }


def ingest_document(chunks, artifacts=None):
    """Run the full merge pipeline over every chunk of an uploaded document."""
    artifacts = artifacts or []

    artifacts_by_page = {}
    for artifact in artifacts:
        artifacts_by_page.setdefault(artifact.get("page_number"), []).append(artifact)

    actions = Counter()
    concepts = set()
    failures = []

    for chunk in chunks:
        try:
            outcome = process_extracted_chunk(
                chunk, artifacts_by_page.get(chunk.get("page_number"), [])
            )
        except Exception as exc:
            logger.exception("Chunk %s failed to process.", chunk.get("chunk_id"))
            actions["failed"] += 1
            failures.append({"chunk_id": chunk.get("chunk_id"), "error": str(exc)})
            continue
        actions[outcome["action"]] += 1
        concepts.add(outcome["concept_id"])

    return {
        "chunks_processed": len(chunks),
        "actions": dict(actions),
        "concepts_touched": sorted(concepts),
        "failures": failures,
    }


# --------------------------------------------------------------------------- #
# Graph reads
# --------------------------------------------------------------------------- #

FULL_GRAPH_CYPHER = """
MATCH (c:Concept)
OPTIONAL MATCH (c)-[:HAS_FACT]->(f:Fact)
WITH c, count(DISTINCT f) AS fact_count
OPTIONAL MATCH (c)-[:HAS_ARTIFACT]->(a:Artifact)
WITH c, fact_count, count(DISTINCT a) AS artifact_count
OPTIONAL MATCH (c)-[r:RELATES_TO]->(target:Concept)
RETURN c.id AS id, c.title AS title, fact_count, artifact_count,
       target.id AS target_id, r.type AS relation
ORDER BY c.title
"""

CONCEPT_FACTS_CYPHER = """
MATCH (c:Concept {id: $concept_id})-[:HAS_FACT]->(f:Fact)
OPTIONAL MATCH (f)-[:EXTRACTED_FROM]->(s:Source)
WITH c, f, collect(DISTINCT {
  file_name: s.file_name,
  location_tag: s.location_tag,
  raw_snippet: s.raw_snippet
}) AS sources ORDER BY f.created_at
RETURN c.title AS concept_title,
       f.id AS fact_id,
       f.text AS fact_text,
       sources
"""

CONCEPT_ARTIFACTS_CYPHER = """
MATCH (c:Concept {id: $concept_id})-[:HAS_ARTIFACT]->(a:Artifact)
RETURN a.id AS id, a.image_url AS image_url, a.file_name AS file_name,
       a.location_tag AS location_tag, a.caption AS caption
ORDER BY a.created_at
"""


def fetch_full_graph() -> dict:
    """Return graph elements formatted directly for the React Flow canvas."""
    with get_driver().session() as session:
        records = list(session.run(FULL_GRAPH_CYPHER))

    nodes = {}
    edges = {}

    for record in records:
        concept_id = record["id"]
        if concept_id not in nodes:
            nodes[concept_id] = {
                "id": concept_id,
                "type": "customConceptNode",
                "data": {
                    "label": record["title"] or "Untitled Concept",
                    "factCount": record["fact_count"] or 0,
                    "artifactCount": record["artifact_count"] or 0,
                },
            }

        target_id = record["target_id"]
        if target_id:
            edge_id = f"e-{concept_id}-{target_id}"
            edges[edge_id] = {
                "id": edge_id,
                "source": concept_id,
                "target": target_id,
                "label": record["relation"] or "relates_to",
                "animated": True,
            }

    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def fetch_concept_lineage(concept_id: str) -> dict:
    """Retrieve all synthesized facts, citations and artifacts for one concept."""
    with get_driver().session() as session:
        fact_records = list(session.run(CONCEPT_FACTS_CYPHER, concept_id=concept_id))
        artifact_records = list(
            session.run(CONCEPT_ARTIFACTS_CYPHER, concept_id=concept_id)
        )
        if not fact_records:
            title_record = session.run(
                "MATCH (c:Concept {id: $concept_id}) RETURN c.title AS title",
                concept_id=concept_id,
            ).single()
            title = (title_record["title"] if title_record else "") or ""
        else:
            title = ""
    facts = []
    for record in fact_records:
        title = record["concept_title"] or title
        facts.append(
            {
                "fact_id": record["fact_id"],
                "text": record["fact_text"],
                "sources": [
                    source
                    for source in record["sources"]
                    if source["file_name"] is not None
                ],
            }
        )

    return {
        "id": concept_id,
        "title": title,
        "facts": facts,
        "artifacts": [dict(artifact) for artifact in artifact_records],
    }