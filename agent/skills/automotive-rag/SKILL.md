---
name: automotive-rag
description: Enforces ASPICE (SWE.1 to SWE.4), ISO 26262 functional safety, and Eclipse S-CORE C++ guidelines by performing Agentic RAG over MongoDB Atlas. Use when analyzing, enhancing, or generating automotive software components, specifications, or verification tests.
---

# Automotive RAG Skill (Eclipse S-CORE & ASPICE)

## Goal
Guide the Antigravity Agent to retrieve automotive specifications, safety analyses, and C++ guidelines from MongoDB Atlas, and apply them rigorously to produce production-grade, ASIL-compliant software artifacts.

## Available Tools (from `mongodb_atlas` MCP Server)
- `atlas_vector_search(query: str, limit: int = 5, process_area: Optional[str] = None)`:
  Performs hybrid semantic similarity search using Voyage AI embeddings over indexed Eclipse S-CORE documents.
- `atlas_get_document(doc_id: str)`:
  Fetches the complete text of any indexed specification, template, or diagram.
- `atlas_find(filter_json: str, limit: int = 5)`:
  Direct MQL query for exact keyword or metadata filtering.

## Multi-Phase Agentic Retrieval Workflow

When asked to construct, review, or enhance an automotive component, execute the following retrieval sequence:

### Phase 1: Requirements & Safety Analysis (ASPICE SWE.1)
1. **Query Failure Modes and Control Measures**:
   - Call `atlas_vector_search(query="failure modes control measures queue overflow thread safety", limit=3)`
   - Identify safety requirements: bounded buffer limits, overflow policy (drop oldest vs. reject newest), and lock-free or deterministic latency constraints.
2. **Retrieve Requirements Directives**:
   - Query Sphinx-Needs or TRLC requirement format: `atlas_vector_search(query="Sphinx-Needs requirement template req id status", limit=2)`

### Phase 2: Software Architecture & Detailed Design (ASPICE SWE.2 / SWE.3)
1. **C++ Memory & Concurrency Guidelines**:
   - Query C++ policies: `atlas_vector_search(query="non allocating memory policy fixed size buffer real time", limit=3)`
   - Enforce automotive rules:
     - Zero dynamic memory allocation (`new`, `malloc`, `std::vector::resize`) during operational phase.
     - Safe concurrency mechanisms without unmonitored priority inversion.
     - `noexcept` specifications on critical path functions.
2. **Component Interface Design**:
   - Match Eclipse S-CORE namespace standards: `namespace score::message_passing` or similar.

### Phase 3: Unit Verification (ASPICE SWE.4)
1. **Retrieve Verification Specifications**:
   - Query unit test patterns: `atlas_vector_search(query="timed command queue test cases boundary conditions GoogleTest", limit=3)`
2. **Construct Comprehensive Test Vectors**:
   - GoogleTest (`TEST_F`, `EXPECT_TRUE`, `EXPECT_EQ`).
   - Boundary checks: queue full, queue empty, concurrency stress, overflow policy validation.

### Phase 4: Bi-Directional Traceability
- Ensure every unit test explicitly cites the requirement ID it verifies (e.g. `// Verifies: REQ_TIMED_QUEUE_BOUNDED_CAPACITY_001`).

## Example Tool Invocations

```json
{
  "tool": "atlas_vector_search",
  "args": {
    "query": "Bounded queue capacity overflow policy ASIL-B safety requirements",
    "limit": 3
  }
}
```

```json
{
  "tool": "atlas_vector_search",
  "args": {
    "query": "non-allocating future memory policies C++ real-time",
    "limit": 3
  }
}
```
