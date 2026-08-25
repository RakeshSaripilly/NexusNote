import os
import json
import uuid
from dotenv import load_dotenv
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
import ollama

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

embedder = SentenceTransformer('all-MiniLM-L6-v2')

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD),
    max_connection_lifetime=30*60,
    max_connection_pool_size=50
)

def init_vector_index():
    query = """
    CREATE VECTOR INDEX factVectors IF NOT EXISTS
    FOR (f:Fact) ON (f.embedding)
    OPTIONS {indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
    } }
    """

    with driver.session() as session:
        session.run(query)
    print("Neo4J vector index 'factVectors' verified.")

def get_embedding(text):
    return embedder.encode(text).toList()

def query_vector_match(embedding,threshold:float=0.82):
    query = """
    CALL db.index.vector.query('factVectors',1,$embedding)
    YIELD node AS f, score
    WHERE score >= $threshold
    MATCH (c:Concept)-[:HAS_FACT]->(f)
    RETURN c.id AS concept_id, c.title AS concept_title, f.id AS fact_id, f.text AS fact_text, score
    LIMIT 1
    """
    with driver.session() as session:
        result = session.run(query,embedding=embedding,threshold=threshold)
        record = result.single()
        return dict(record) if record else None

SYSTEM_DECISION_PROMPT = """You are a knowledge graph synthesizer. 
Compare the NEW CHUNK with the EXISTING TOPIC and FACT.
Return ONLY a JSON object with one of these exact structures:

1. If duplicate:
{"action": "MERGE_SOURCE"}

2. If new fact under same topic:
{"action": "EXTEND_NODE", "synthesized_fact": "one sentence summary"}

3. If new related subtopic:
{"action": "SPIN_OFF_NODE", "new_concept": "Short Title", "relation": "relates_to", "synthesized_fact": "one sentence summary"}
"""
def process_extracted_chunk(chunk):
    embedding = get_embedding(chunk["text"])
    match = query_vector_match(embedding)

    with driver.session() as session:
        if match:
            # If a match is found, use the existing concept and fact
            user_prompt = f"Existing Concept: {match['concpet_title']}\nExisting FACT: {match['fact_text']}\nNew Chunk: {chunk['text']}\n"
            try:
                res = ollama.chat(
                    model=OLLAMA_MODEL,
                    messages=[
                        {"role":"system","content":SYSTEM_DECISION_PROMPT},
                        {"role":"user","content":user_prompt}
                    ],
                    format="json"
                )
                decision = json.loads(res["message"]["content"])
            except Exception:
                decision = {"action":"EXTEND_NODE","synthesized_fact":chunk["text"]}
            action = decision.get("action")

            if action == "MERGE_SOURCE":
                cypher = """
                MATCH (f:Fact {id:$fact_id})
                CREATE (s:Source {
                id:$source_id,
                filename:$file_name,
                location_tag:$loc,
                raw_snippet:$snippet,
                uploaded_at:datetime()
                })
                CREATE (f)-[:EXTRACTED_FROM]->(s)
                """
                session.run(cypher,fact_id=match["fact_id"],source_id=str(uuid.uuid4()),file_name=chunk["file_name"],loc=chunk["location_tag"],snippet=chunk["raw_snippet"])
            elif action == "EXTEND_NODE":
                fact_text = decision.get("synthesized_fact", chunk["text"])
                fact_emb = get_embedding(fact_text)
                cypher = """
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
                    location_tag: $loc,
                    raw_snippet: $snippet,
                    uploaded_at: datetime()
                })
                CREATE (c)-[:HAS_FACT]->(f)
                CREATE (f)-[:EXTRACTED_FROM]->(s)
                """
                session.run(cypher, concept_id=match["concept_id"], fact_id=str(uuid.uuid4()),
                            fact_text=fact_text, embedding=fact_emb, source_id=str(uuid.uuid4()),
                            file_name=chunk["file_name"], loc=chunk["location_tag"], snippet=chunk["raw_snippet"])

            elif action == "SPIN_OFF_NODE":
                # Create child concept node, fact, source, and relationship edge
                new_concept = decision.get("new_concept", "Sub Topic")
                fact_text = decision.get("synthesized_fact", chunk["text"])
                fact_emb = get_embedding(fact_text)
                cypher = """
                MATCH (parent:Concept {id: $parent_id})
                MERGE (child:Concept {title: $new_concept})
                  ON CREATE SET child.id = $new_concept_id, child.created_at = datetime()
                CREATE (f:Fact {
                    id: $fact_id,
                    text: $fact_text,
                    embedding: $embedding,
                    created_at: datetime()
                })
                CREATE (s:Source {
                    id: $source_id,
                    file_name: $file_name,
                    location_tag: $loc,
                    raw_snippet: $snippet,
                    uploaded_at: datetime()
                })
                CREATE (child)-[:HAS_FACT]->(f)
                CREATE (f)-[:EXTRACTED_FROM]->(s)
                MERGE (child)-[:RELATES_TO {type: $relation}]->(parent)
                """
                session.run(cypher, parent_id=match["concept_id"], new_concept=new_concept,
                            new_concept_id=str(uuid.uuid4()), fact_id=str(uuid.uuid4()),
                            fact_text=fact_text, embedding=fact_emb, source_id=str(uuid.uuid4()),
                            file_name=chunk["file_name"], loc=chunk["location_tag"],
                            snippet=chunk["raw_snippet"], relation=decision.get("relation", "relates_to"))

        else:
            # No semantic match -> Create brand new Concept node
            extract_prompt = f"Extract a short concept topic title (2-4 words) and a clean fact from this text: '{chunk['text']}'. Output JSON: {{\"concept\": \"...\", \"fact\": \"...\"}}"
            try:
                res = ollama.chat(
                    model=OLLAMA_MODEL,
                    messages=[{"role": "user", "content": extract_prompt}],
                    format="json"
                )
                info = json.loads(res["message"]["content"])
            except Exception:
                info = {"concept": "General Concept", "fact": chunk["text"]}

            concept_title = info.get("concept", "General Concept")
            fact_text = info.get("fact", chunk["text"])
            fact_emb = get_embedding(fact_text)

            cypher = """
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
                location_tag: $loc,
                raw_snippet: $snippet,
                uploaded_at: datetime()
            })
            CREATE (c)-[:HAS_FACT]->(f)
            CREATE (f)-[:EXTRACTED_FROM]->(s)
            """
            session.run(cypher, concept_title=concept_title, concept_id=str(uuid.uuid4()),
                        fact_id=str(uuid.uuid4()), fact_text=fact_text, embedding=fact_emb,
                        source_id=str(uuid.uuid4()), file_name=chunk["file_name"],
                        loc=chunk["location_tag"], snippet=chunk["raw_snippet"])
def fetch_full_graph() -> dict:
    """
    Returns graph elements formatted directly for React Flow canvas.
    """
    query = """
    MATCH (c:Concept)
    OPTIONAL MATCH (c)-[:HAS_FACT]->(f:Fact)
    WITH c, count(f) AS fact_count
    OPTIONAL MATCH (c)-[r:RELATES_TO]->(target:Concept)
    RETURN c.id AS id, c.title AS title, fact_count, target.id AS target_id, r.type AS relation
    """
    with driver.session() as session:
        results = session.run(query)
        nodes_dict = {}
        edges = []

        for record in results:
            cid = record["id"]
            if cid not in nodes_dict:
                nodes_dict[cid] = {
                    "id": cid,
                    "type": "customConceptNode",
                    "data": {"label": record["title"], "factCount": record["fact_count"]},
                    "position": {
                        "x": 100 + (len(nodes_dict) * 200) % 700,
                        "y": 100 + (len(nodes_dict) * 140) % 500
                    }
                }
            if record["target_id"]:
                edges.append({
                    "id": f"e-{cid}-{record['target_id']}",
                    "source": cid,
                    "target": record["target_id"],
                    "label": record["relation"] or "relates_to",
                    "animated": True
                })

        return {"nodes": list(nodes_dict.values()), "edges": edges}

def fetch_concept_lineage(concept_id: str) -> dict:
    """
    Retrieves all synthesized facts and source citations for a specific concept.
    """
    query = """
    MATCH (c:Concept {id: $concept_id})-[:HAS_FACT]->(f:Fact)
    OPTIONAL MATCH (f)-[:EXTRACTED_FROM]->(s:Source)
    RETURN c.title AS concept_title, f.id AS fact_id, f.text AS fact_text,
           collect({
               file_name: s.file_name,
               location_tag: s.location_tag,
               raw_snippet: s.raw_snippet
           }) AS sources
    """
    with driver.session() as session:
        results = session.run(query, concept_id=concept_id)
        facts = []
        concept_title = ""
        for record in results:
            concept_title = record["concept_title"]
            facts.append({
                "fact_id": record["fact_id"],
                "text": record["fact_text"],
                "sources": [src for src in record["sources"] if src["file_name"] is not None]
            })
            
        return {"id": concept_id, "title": concept_title, "facts": facts}