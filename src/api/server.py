from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import threading
from src.api.engine import rag_engine 
from src.telemetry import log_feedback, get_telemetry

# Initialize the App
app = FastAPI(
    title="Layer10 Graph Memory API",
    description="A GraphRAG system that retrieves knowledge from GitHub Issues using Neo4j + Vector Search.",
    version="1.0"
)

# Define the Input Format
class QueryRequest(BaseModel):
    question: str

# Define the Output Format
class QueryResponse(BaseModel):
    answer: str
    context_used: str

class FeedbackRequest(BaseModel):
    is_positive: bool

@app.on_event("startup")
async def startup_event():
    """
    Initialize the DB connection and Indexing on startup.
    """
    print("🚀 Server Starting... Indexing Graph Nodes in the background...")
    try:
        threading.Thread(target=rag_engine.index_entities, daemon=True).start()
    except Exception as e:
        print(f"⚠️ Indexing Warning: {e}")

@app.post("/query", response_model=QueryResponse)
async def ask_question(request: QueryRequest):
    """
    The Main Endpoint: Receives a question -> Runs GraphRAG -> Returns Answer.
    """
    try:
        # 1. Get Context (Raw Graph Data)
        context = rag_engine.retrieve_context(request.question)
        
        if not context:
            return QueryResponse(
                answer="I couldn't find any relevant info in the Knowledge Graph.",
                context_used="None"
            )

        # 2. Get LLM Answer
        answer = rag_engine.answer_question(request.question)
        
        # 3. Return both (Transparency)
        return QueryResponse(
            answer=answer,
            context_used=context
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    """
    Endpoint to receive Thumbs Up/Down feedback from the UI.
    """
    log_feedback(req.is_positive)
    return {"status": "recorded"}

@app.get("/telemetry")
def read_telemetry():
    """
    Endpoint to serve telemetry data to the UI dashboard.
    """
    return get_telemetry()

@app.get("/")
def health_check():
    return {"status": "active", "system": "GraphRAG v1"}