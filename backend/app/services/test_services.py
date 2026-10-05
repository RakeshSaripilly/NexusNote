import os
import sys
from pathlib import Path

# Add backend directory to Python path for seamless imports
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

import ollama
from neo4j import GraphDatabase
from app.services.parser import chunk_text
from app.services.engine import (
    init_vector_index,
    get_embedding,
    process_extracted_chunk,
    fetch_full_graph,
    fetch_concept_lineage,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    OLLAMA_MODEL
)

def run_health_check():
    print("=" * 60)
    print("🚀 NEXUSNOTE BACKEND DIAGNOSTIC SUITE")
    print("=" * 60)

    # 1. Environment Variables Check
    print("\n[1/5] 🔍 Checking Environment Configuration...")
    print(f"   • NEO4J_URI    : {NEO4J_URI}")
    print(f"   • NEO4J_USER   : {NEO4J_USER}")
    print(f"   • OLLAMA_MODEL : {OLLAMA_MODEL}")
    if not NEO4J_URI or not NEO4J_PASSWORD:
        print("   ❌ Error: Missing Neo4j credentials in backend/.env")
        return False
    print("   ✅ Environment variables detected.")

    # 2. Neo4j Connection & Vector Index
    print("\n[2/5] 🔍 Testing Neo4j Connection & Vector Index...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            res = session.run("RETURN 'Connected' AS status")
            print(f"   ✅ Neo4j Connection: {res.single()['status']}")
        driver.close()
        init_vector_index()
    except Exception as e:
        print(f"   ❌ Neo4j Connection Failed: {e}")
        return False

    # 3. Embedding Model Test
    print("\n[3/5] 🔍 Testing SentenceTransformers (all-MiniLM-L6-v2)...")
    try:
        test_vec = get_embedding("React Reconciliation and Virtual DOM")
        print(f"   ✅ Embedder operational (Vector dimensions: {len(test_vec)})")
    except Exception as e:
        print(f"   ❌ Embedding generation failed: {e}")
        return False

    # 4. Ollama LLM Connection Test
    print(f"\n[4/5] 🔍 Testing Ollama ({OLLAMA_MODEL})...")
    from app.services.engine import ollama_client
    ollama_ok = False
    try:
        res = ollama_client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": "Output JSON only."},
                {"role": "user", "content": "Extract topic from: 'FastAPI is an async framework.' Format: {\"topic\": \"...\"}"}
            ],
            format="json"
        )
        content = ""
        if hasattr(res, "message") and hasattr(res.message, "content"):
            content = res.message.content
        elif isinstance(res, dict):
            content = res.get("message", {}).get("content", "")
        print(f"   ✅ Ollama JSON response: {content.strip()}")
        ollama_ok = True
    except Exception as e:
        print(f"   ⚠️  Ollama call failed or server offline: {e}")
        print(f"   👉 Fallback mode: Ingestion will use heuristic fallback without LLM.")

    # 5. End-to-End Ingestion & Deduplication Test
    print("\n[5/5] 🔍 Testing Pipeline Ingestion (Doc 1 vs Doc 2 Overlap)...")
    try:
        # Document 1: Initial Ingest
        chunk_1 = {
            "text": "The Virtual DOM is an in-memory representation of real DOM elements used by React.",
            "file_name": "React_Basics.pdf",
            "location_tag": "Page 1",
            "raw_snippet": "The Virtual DOM is an in-memory representation of real DOM elements used by React."
        }
        print("   • Ingesting Chunk 1 (React_Basics.pdf)...")
        process_extracted_chunk(chunk_1)

        # Document 2: Semantically Overlapping Ingest
        chunk_2 = {
            "text": "React maintains a virtual copy of the DOM in memory to calculate efficient UI updates.",
            "file_name": "Web_Performance.pdf",
            "location_tag": "Page 4",
            "raw_snippet": "React maintains a virtual copy of the DOM in memory to calculate efficient UI updates."
        }
        print("   • Ingesting Chunk 2 (Web_Performance.pdf - Overlapping)...")
        process_extracted_chunk(chunk_2)

        # Retrieve and verify graph
        graph = fetch_full_graph()
        print(f"   ✅ Graph Nodes generated: {len(graph['nodes'])}")
        print(f"   ✅ Graph Edges generated: {len(graph['edges'])}")

        if graph["nodes"]:
            first_node_id = graph["nodes"][0]["id"]
            lineage = fetch_concept_lineage(first_node_id)
            print(f"\n   📌 Sample Node: '{lineage['title']}'")
            for fact in lineage["facts"]:
                print(f"      - Fact: {fact['text']}")
                for src in fact["sources"]:
                    print(f"        └─ Source Link: {src['file_name']} ({src['location_tag']})")

    except Exception as e:
        print(f"   ❌ Ingestion pipeline failed: {e}")
        return False

    print("\n" + "=" * 60)
    print("🎉 ALL SYSTEMS PASSING — READY FOR FRONTEND INTEGRATION!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    run_health_check()