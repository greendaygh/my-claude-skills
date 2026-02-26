# literature-knowledge-graph

Build Neo4j knowledge graphs from scientific literature using expert panel discussion + 2-cycle iterative refinement. This skill should be used when the user asks to "build a knowledge graph from literature", "extract entities and relationships from papers", "create a literature-based knowledge graph", or "mine scientific papers for knowledge graph construction".

## Trigger Phrases
- "build a knowledge graph from literature"
- "extract entities from papers"
- "literature knowledge graph"
- "mine papers into a graph database"
- "create a Neo4j graph from research papers"

## Prerequisites

```bash
pip install -r ~/.claude/skills/literature-knowledge-graph/requirements.txt
```

Neo4j must be running (see `references/neo4j_setup.md` for Docker setup):
```bash
docker run -d --name neo4j-kg -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  -e NEO4J_PLUGINS='["graph-data-science"]' \
  neo4j:5-community
```

## Architecture: 2-Cycle Iterative Refinement

```
━━━ Cycle 1: Initial Exploration ━━━
  Phase 1  → Initial schema + panel config
  Phase 2  → Panel Round 1: search strategy + schema review
  Phase 3  → Literature search + full-text collection
  Phase 4  → Entity/relationship extraction (initial schema)
  Phase 5  → Panel Round 2: extraction validation + schema_delta
━━━ Cycle 2: Refinement ━━━
  Phase 6  → Schema refinement (apply schema_delta)
  Phase 7  → Panel Round 3: refined strategy + supplemental search
  Phase 8  → Supplemental search + re-extraction
  Phase 9  → Panel Round 4: final validation + consensus
━━━ Final ━━━
  Phase 10 → Neo4j graph construction
  Phase 11 → Query, analysis, visualization
  Phase 12 → Automated monitoring (optional)
```

---

## Phase 1: Initial Schema + Panel Configuration

### 1a. Define Schema

Ask the user for their domain and research goal. Then:

1. Copy `~/.claude/skills/literature-knowledge-graph/assets/schema_template.json` to the project working directory as `schema_v1.0.json`
2. Consult `references/schema_patterns.md` for domain-specific patterns
3. Customize entity_types and relationship_types for the user's domain
4. Set project name and description
5. Tell the user this schema is **provisional** — it will be refined in Cycle 2

### 1b. Configure Expert Panel

1. Copy `~/.claude/skills/literature-knowledge-graph/assets/panel_config.json` to the project directory
2. Adjust expert personas to match the domain (e.g., for drug discovery, make the domain expert a medicinal chemist)
3. Present the panel to the user

### Expert Panel Members

| Expert | Role | Focus |
|--------|------|-------|
| Domain Expert | Deep field knowledge | Core entities/relations, terminology |
| Methodologist | Research design evaluation | Paper quality, experimental design, reproducibility |
| Statistician | Quantitative analysis | Effect sizes, significance, data quality |
| Critical Reviewer | Counterarguments/limitations | Bias detection, missing relations, over-interpretation |

---

## Phase 2: Panel Round 1 — Search Strategy + Schema Review

Launch 4 expert agents **in parallel** using Task tool:

```
For EACH expert, call Task tool with:
  subagent_type: general-purpose
  description: "{expert_name} Round 1"
  prompt: |
    You are a {expert_persona}.

    ## Domain
    {domain_description}

    ## Current Schema (v1.0)
    {schema_json}

    ## Your Tasks (Round 1 — Search Strategy + Schema Review):
    1. Recommend search keywords and MeSH terms for this domain
    2. Suggest inclusion/exclusion criteria for papers
    3. Review the initial schema:
       - Any missing entity types or relationship types?
       - Any unnecessary/redundant items?
       - Any properties that should be added?

    Respond concisely (3-5 sentences per task).
```

After all 4 return, **synthesize consensus**:
- Compile agreed search queries
- Apply schema feedback where 3+ experts agree → produce `schema_v1.1.json`
- Document disagreements

**Output**: Search query list + schema v1.1

---

## Phase 3: Literature Search + Full-Text Collection

### 3a. Literature Search

Use the agreed search queries from Phase 2. For each query, invoke the relevant database skills:

1. **PubMed**: Use `scientific-skills:pubmed-database` skill
2. **bioRxiv**: Use `scientific-skills:biorxiv-database` skill
3. **OpenAlex**: Use `scientific-skills:openalex-database` skill

Alternatively, use the integrated search script:
```bash
python ~/.claude/skills/literature-knowledge-graph/scripts/search_literature.py \
  --queries "query1,query2,query3" \
  --max-results 50 \
  --date-from 2020-01-01 \
  --output papers.json
```

The script handles deduplication (DOI + title similarity).

### 3b. Full-Text Collection

```bash
python ~/.claude/skills/literature-knowledge-graph/scripts/fetch_fulltext.py \
  --papers papers.json \
  --output-dir ./fulltext/ \
  --max-concurrent 3
```

This fetches:
- **PMC XML** → structured section-by-section full text
- **bioRxiv PDF** → markitdown markdown conversion
- **User PDFs** → pypdf/markitdown parsing (use `--local-pdfs ./pdfs/`)
- **Fallback** → abstract only (confidence penalty -0.2)

Output: Per-paper structured JSON with sections (abstract, introduction, methods, results, discussion, figures_tables).

See `references/fulltext_access.md` for details on access methods.

---

## Phase 4: Entity/Relationship Extraction (Initial Schema)

For each paper's **full text**, generate extraction prompts dynamically from schema v1.1:

1. Read the extraction prompt template from `references/extraction_prompts.md`
2. Populate the template with entity_types and relationship_types from schema v1.1
3. Feed each paper's full text sections to Claude for extraction
4. Apply confidence scores based on source section:
   - Results (direct experiment): 0.9
   - Results (statistical inference): 0.8
   - Abstract: 0.85
   - Introduction (background): 0.8 (mark is_background: true)
   - Discussion (interpretation): 0.6
   - Discussion (hypothesis): 0.4
5. Record **unschemaed discoveries**: entities/relations not in the schema, tagged with `_unschemaed`

**Extraction prompt pattern** (for each paper):

```
You are an expert at extracting structured knowledge from scientific literature.

## Schema
[Entity types and relationship types from schema v1.1]

## Paper Full Text
### Abstract: {text}
### Introduction: {text}
### Methods: {text}
### Results: {text}
### Discussion: {text}
### Figures/Tables: {captions}

## Rules
1. Normalize entity names (official symbols/terms)
2. Assign confidence based on section and evidence strength
3. Record source_section and evidence quote for each extraction
4. Also capture entities/relations NOT in the schema under "unschemaed"

Output JSON format:
{
  "entities": [...],
  "relationships": [...],
  "unschemaed": [...]
}
```

**Output**: Initial extraction results JSON + list of unschemaed discoveries

---

## Phase 5: Panel Round 2 — Extraction Validation + Schema Improvement

**This is the key output of Cycle 1**: validated extractions + schema_delta.

Launch 4 experts **in parallel**:

```
For EACH expert, call Task tool with:
  subagent_type: general-purpose
  description: "{expert_name} Round 2"
  prompt: |
    You are a {expert_persona}.

    ## Previous Round 1 Consensus
    {round_1_consensus_summary}

    ## Extraction Results Summary
    - Total entities extracted: {count}
    - Entity types: {type_distribution}
    - Total relationships: {count}
    - Relationship types: {type_distribution}
    - Sample extractions: {top_10_examples}

    ## Unschemaed Discoveries
    {unschemaed_list}

    ## Current Schema (v1.1)
    {schema_json}

    ## Your Tasks (Round 2 — Validation + Schema Improvement):
    1. Evaluate extraction quality: identify incorrect entities/relationships
    2. Identify missing extractions
    3. Propose schema changes (schema_delta):
       - New entity types to add (from unschemaed discoveries)
       - Entity properties to add/modify
       - New relationship types to add
       - Items to remove (over-engineering)
       - Additional search keywords for Cycle 2

    Respond concisely. Be specific with schema_delta proposals.
```

After synthesis, produce **schema_delta**:
```json
{
  "add_entity_types": [...],
  "modify_entity_types": [...],
  "remove_entity_types": [...],
  "add_relationship_types": [...],
  "modify_relationship_types": [...],
  "remove_relationship_types": [...],
  "additional_search_queries": [...],
  "extraction_notes": [...]
}
```

**Output**: Validated Cycle 1 extractions + schema_delta

---

## ═══ CYCLE 2: REFINEMENT ═══

## Phase 6: Schema Refinement

Apply the schema_delta from Phase 5:

1. Load schema_v1.1.json
2. Apply each change from schema_delta
3. Save as `schema_v2.0.json`
4. Log changes:
   ```
   Schema v2.0 Changes:
   + Added entities: Pathway, CellLine
   ~ Modified entities: Gene (added properties: function, pathway_membership)
   + Added relationships: PARTICIPATES_IN (Gene→Pathway)
   - Removed: none
   ```

---

## Phase 7: Panel Round 3 — Refined Strategy

Launch 4 experts **in parallel**:

```
For EACH expert, call Task tool with:
  subagent_type: general-purpose
  description: "{expert_name} Round 3"
  prompt: |
    You are a {expert_persona}.

    ## Cycle 1 Summary
    {cycle_1_consensus_summary}

    ## Schema Changes (v1.1 → v2.0)
    {schema_delta_summary}

    ## Refined Schema (v2.0)
    {schema_v2_json}

    ## Your Tasks (Round 3 — Refined Strategy):
    1. Confirm the refined schema v2.0 is appropriate
    2. Identify areas needing supplemental search
    3. Decide re-extraction scope:
       - Full re-extraction of all papers?
       - Only extract newly added entity/relationship types?
       - Which Cycle 1 results to keep vs. discard?

    Respond concisely (3-5 sentences per task).
```

**Output**: Supplemental search queries + re-extraction scope decision

---

## Phase 8: Supplemental Search + Re-extraction

### 8a. Supplemental Literature Search (if needed)

Search for papers in areas identified by Round 3:

```bash
python ~/.claude/skills/literature-knowledge-graph/scripts/search_literature.py \
  --queries "new_query1,new_query2" \
  --exclude-dois existing_papers_dois.json \
  --output supplemental_papers.json
```

Fetch full text for new papers.

### 8b. Re-extraction with Refined Schema v2.0

1. **Changed types only**: Re-scan existing papers for newly added entity/relationship types
2. **New papers**: Full extraction with complete schema v2.0
3. **Merge**: Combine Cycle 1 results with Cycle 2 additions
4. Tag each extraction with `extraction_cycle: 1` or `extraction_cycle: 2`

Use the Cycle 2 supplemental extraction prompt from `references/extraction_prompts.md`.

**Output**: Merged extraction results (Cycle 1 + Cycle 2)

---

## Phase 9: Panel Round 4 — Final Validation + Consensus

**Final quality gate**. Launch 4 experts **in parallel**:

```
For EACH expert, call Task tool with:
  subagent_type: general-purpose
  description: "{expert_name} Round 4 Final"
  prompt: |
    You are a {expert_persona}.

    ## Full Context
    - Cycle 1→2 evolution summary: {evolution_summary}
    - Schema v2.0: {schema_json}
    - Total papers analyzed: {count}
    - Full text available: {ft_count} / Abstract only: {abs_count}

    ## Merged Extraction Results
    - Entities: {entity_summary_by_type}
    - Relationships: {rel_summary_by_type}
    - Cycle 1 items: {c1_count} / Cycle 2 additions: {c2_count}
    - Sample extractions: {examples}

    ## Your Final Review Tasks (Round 4):
    {expert_specific_tasks}

    For each reviewed item, assign a panel_confidence score (0-1).
    Flag any items that should be removed or modified.

    Respond with:
    1. Items to modify/remove (with reasons)
    2. panel_confidence scores for entity types
    3. Key findings and limitations (2-3 sentences)
```

Expert-specific tasks:
- **Domain Expert**: Entity name normalization final check, relationship type consistency
- **Methodologist**: Evidence level final assessment, reproducibility concerns
- **Statistician**: Quantitative data consistency, contradiction/duplicate detection
- **Critical Reviewer**: Overall graph bias assessment, missing key relationships, over-extraction

If disagreements exist, request a **second round of discussion** (additional Task calls).

**Output**:
- Final validated extractions with `panel_verified: true`
- `panel_confidence` scores per entity/relationship
- Final panel report: evolution from Cycle 1→2, key findings, limitations

---

## Phase 10: Neo4j Graph Construction

### 10a. Initialize Neo4j Schema

```bash
python ~/.claude/skills/literature-knowledge-graph/scripts/setup_neo4j.py \
  --password $NEO4J_PASSWORD \
  --schema schema_v2.0.json
```

### 10b. Load Graph

```bash
python ~/.claude/skills/literature-knowledge-graph/scripts/build_graph.py \
  --password $NEO4J_PASSWORD \
  --extractions final_extractions.json \
  --papers papers.json \
  --schema schema_v2.0.json \
  --cycle 2
```

This creates:
- **Paper nodes**: DOI, title, authors, year, journal, full_text_available
- **Entity nodes**: MERGE on primary_key (dedup)
- **Relationships**: with confidence, evidence, source_section
- **:EXTRACTED_FROM** provenance: links every entity/rel to source Paper
- **Metadata**: panel_verified, panel_confidence, extraction_cycle, schema_version

---

## Phase 11: Query, Analysis, Visualization

### Queries

```bash
# Graph statistics
python ~/.claude/skills/literature-knowledge-graph/scripts/query_graph.py \
  --password $NEO4J_PASSWORD --query stats

# Neighbors of a node
python ~/.claude/skills/literature-knowledge-graph/scripts/query_graph.py \
  --password $NEO4J_PASSWORD --query neighbors --node "TP53" --node-label Gene --depth 2

# Shortest paths
python ~/.claude/skills/literature-knowledge-graph/scripts/query_graph.py \
  --password $NEO4J_PASSWORD --query paths --node "TP53,Breast Cancer"

# Most central nodes
python ~/.claude/skills/literature-knowledge-graph/scripts/query_graph.py \
  --password $NEO4J_PASSWORD --query central --limit 20

# Community detection
python ~/.claude/skills/literature-knowledge-graph/scripts/query_graph.py \
  --password $NEO4J_PASSWORD --query communities
```

See `references/cypher_queries.md` for the full query template library.

### Community Detection

If Neo4j GDS is installed, use Louvain directly. Otherwise, use `scientific-skills:networkx` skill as fallback.

### Export

```bash
# GraphML (for Gephi)
python ~/.claude/skills/literature-knowledge-graph/scripts/export_graph.py \
  --password $NEO4J_PASSWORD --format graphml --output graph.graphml

# JSON (for D3.js / web viz)
python ~/.claude/skills/literature-knowledge-graph/scripts/export_graph.py \
  --password $NEO4J_PASSWORD --format json --output graph.json

# CSV (for pandas/spreadsheets)
python ~/.claude/skills/literature-knowledge-graph/scripts/export_graph.py \
  --password $NEO4J_PASSWORD --format csv --output graph.csv

# Cytoscape
python ~/.claude/skills/literature-knowledge-graph/scripts/export_graph.py \
  --password $NEO4J_PASSWORD --format cytoscape --output graph.cyjs
```

See `references/visualization.md` for visualization options (Neo4j Browser, pyvis, Gephi, Cytoscape).

---

## Phase 12: Automated Monitoring (Optional)

Set up periodic monitoring for new publications:

### Configure

Create `monitor_state.json`:
```json
{
  "project": "my-project",
  "schema_path": "schema_v2.0.json",
  "schema_version": "v2.0",
  "last_search_date": "2026-02-06",
  "monitoring_queries": ["query1", "query2"],
  "sources": ["pubmed", "biorxiv", "openalex"],
  "max_results_per_query": 20,
  "schedule": "weekly",
  "known_dois": [],
  "output_dir": "./monitor_output"
}
```

### Run

```bash
# Single run
python ~/.claude/skills/literature-knowledge-graph/scripts/monitor.py \
  --config monitor_state.json \
  --neo4j-password $NEO4J_PASSWORD \
  --run-once

# Daemon mode
python ~/.claude/skills/literature-knowledge-graph/scripts/monitor.py \
  --config monitor_state.json \
  --neo4j-password $NEO4J_PASSWORD \
  --daemon
```

New papers go through: search → full-text fetch → extraction (schema v2.0) → simplified panel review (1 round) → graph addition.

---

## Reference Files

| File | Content |
|------|---------|
| `references/neo4j_setup.md` | Docker install, connection, memory, GDS plugin |
| `references/schema_patterns.md` | Domain-specific schema examples (biomedical, drug discovery, genomics, single-cell, CRISPR) |
| `references/cypher_queries.md` | 15+ Cypher query templates (stats, neighbors, paths, centrality, communities) |
| `references/extraction_prompts.md` | LLM extraction prompt templates, section-by-section guidelines, confidence rules |
| `references/expert_panel.md` | Panel roles, 4-round × 2-cycle protocol, consensus method, schema_delta format |
| `references/fulltext_access.md` | PMC XML API, bioRxiv PDF, user PDFs, section parsing strategies |
| `references/visualization.md` | Neo4j Browser, pyvis, Gephi, Cytoscape integration |

## Connected Skills

| Phase | Skill | Usage |
|-------|-------|-------|
| 3, 8 | `scientific-skills:pubmed-database` | PubMed search |
| 3, 8 | `scientific-skills:biorxiv-database` | bioRxiv preprint search |
| 3, 8 | `scientific-skills:openalex-database` | OpenAlex search + citations |
| 3, 8 | `scientific-skills:markitdown` | PDF → Markdown conversion |
| 3, 8 | `scientific-skills:pdf` | PDF text extraction (pypdf) |
| 11 | `scientific-skills:networkx` | Community detection / centrality (if GDS unavailable) |
