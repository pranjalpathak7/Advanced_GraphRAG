# Layer10 Memory Core - Execution Guide

## Live Demo
**[Click Here to Try the Live Application!](https://advancedgraphrag.streamlit.app/)**
*(No installation required. You can explore the interactive knowledge graph topology and test the temporally-aware GraphRAG agent directly in your browser.)*

---

This repository contains a production-ready knowledge graph pipeline designed to ingest unstructured GitHub Issues, perform schema-enforced LLM extraction, deduplicate claims safely, and serve a temporally-aware GraphRAG agent.

## Prerequisites
1. Python 3.10+
2. A running instance of Neo4j AuraDB.
3. Create and activate a Python virtual environment, then install dependencies:

```bash
pip install -r requirements.txt
```

## Option 1: Quick Start (Evaluator Mode)

Use this option to evaluate the project using the pre-extracted JSON data included in the submission folder. This skips the LLM extraction phase and does not require LLM or GitHub API keys.

### 1. Environment Setup

Create a .env file in the root directory with only your Neo4j credentials:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=your_username
NEO4J_PASSWORD=your_password
```

### 2. Load the Graph

Push the pre-extracted nodes and edges to Neo4j, applying lossless array merging for duplicate semantic claims:

```bash
python main.py --load
```

### 3. Resolve Entities

Apply the Tombstone pattern to safely merge synonymous aliases (e.g., "LangChain" and "langchain-ai"):

```bash
python main.py --resolve
```
This will take some time. Please let it run for few minutes.

### 4. Launch the Application

The system uses a decoupled architecture. Open two separate terminals:

Terminal A: Start the GraphRAG Backend

```bash
python main.py --api
```

Terminal B: Start the Memory UI

```bash
python main.py --ui
```

## Compliance & Security (The Tombstone Pattern)

To test the system's ability to handle strict data deletion (GDPR/SOC2) without breaking graph topology, you can run the redactor script on any specific Ticket ID currently in your database:

```bash
python main.py --redact <TICKET_ID>
```

This will permanently scrub the text and PII from the database while leaving the conceptual edges intact. You can view the redacted node in the Streamlit UI.

## Option 2: Full Pipeline (Run From Scratch)

Use this option if you want to test the data ingestion, ChromaDB semantic deduplication, and LLM structured extraction pipelines from scratch.

### 1. Full Environment Setup

Your .env file must include all keys:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=your_username
NEO4J_PASSWORD=your_password
GOOGLE_API_KEY=your_gemini_key
GITHUB_TOKEN=your_github_token_for_rate_limits
```

### 2. Execute the Pipeline

Run the following commands in order:

Step 1: Fetch raw GitHub issues:

```bash
python github_loader.py
```

Step 2: Run LLM extraction & pre-extraction semantic dedup:

```bash
python -m src.extraction.extractor
```

Step 3: Load into Neo4j:

```bash
python main.py --load
```

Step 4: Resolve Entities:

```bash
python main.py --resolve
```

Step 5: Start the API & UI (See Step 4 in Option 1).

## Compliance & Security (The Tombstone Pattern)

To test the system's ability to handle strict data deletion (GDPR/SOC2) without breaking graph topology, you can run the redactor script on any specific Ticket ID currently in your database:

```bash
python main.py --redact <TICKET_ID>
```

This will permanently scrub the text and PII from the database while leaving the conceptual edges intact. You can view the redacted node in the Streamlit UI.  