from app.services.engine import init_vector_index,process_extracted_chunk,fetch_full_graph
init_vector_index()
sample_chunk = {
    "text": "React uses a Reconciliation algorithm to compare the Virtual DOM against the real DOM.",
    "file_name": "React_Guide.pdf",
    "location_tag": "Page 1",
    "raw_snippet": "React uses a Reconciliation algorithm to compare the Virtual DOM against the real DOM."
}

# 3. Process Chunk
print("Processing sample chunk...")
process_extracted_chunk(sample_chunk)

# 4. Fetch the resulting graph
graph = fetch_full_graph()
print(f"Graph nodes populated: {len(graph['nodes'])}")
print(graph)