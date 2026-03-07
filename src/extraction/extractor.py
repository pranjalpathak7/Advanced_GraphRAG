import os
import json
import time
import warnings
from typing import Optional

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
import chromadb
from pydantic import ValidationError
from src.telemetry import log_extraction

from src.schema.models import TicketNode, ExtractionResult
warnings.filterwarnings("ignore", category=UserWarning)

load_dotenv()

INPUT_DIR = "data/raw_issues"
OUTPUT_DIR = "data/extracted"
MODEL_NAME = "gemini-2.5-flash"  

# --- Define the extraction version ---
SCHEMA_VERSION = "v1.0"
EXTRACTION_VERSION = f"{SCHEMA_VERSION}-{MODEL_NAME}"  

# --- Setup LLM ---
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("❌ GOOGLE_API_KEY is missing!")

llm = ChatGoogleGenerativeAI(
    model=MODEL_NAME,
    google_api_key=api_key,
    temperature=0  # Deterministic output is best for extraction
)

# Bind the schema to the LLM
structured_llm = llm.with_structured_output(ExtractionResult)

# We use a persistent local vector store to remember processed tickets
print("📦 Initializing Semantic Dedup Cache...")
embed_fn = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
chroma_client = chromadb.PersistentClient(path="./data/chroma_dedup")
dedup_collection = chroma_client.get_or_create_collection(
    name="ticket_dedup",
    metadata={"hnsw:space": "cosine"}
)

# --- The System Prompt ---
system_prompt = """
You are an expert Knowledge Graph Engineer. Your task is to extract structured knowledge from GitHub Issues.

STRICT RULES:
1. **Entities**: Extract only significant technical concepts, technologies, or people. Avoid generic words like "Issue", "Bug", "User".
2. **Relations**: Connect entities logically. 
   - If A causes a bug in B, use label 'AFFECTS'.
   - If A uses B, use 'USES'.
   - If A is a feature of B, use 'RELATED_TO'.
3. **Evidence**: You MUST quote the original text exactly for the 'evidence' field. Do not paraphrase.
4. **Context**: If the text mentions "I" or "me", infer who that is from the author name provided in the prompt context.

Analyze the following Issue carefully:
"""

prompt_template = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "Title: {title}\nAuthor: {author}\n\nBody:\n{body}"),
])

# Combine prompt + LLM
extraction_chain = prompt_template | structured_llm

def check_semantic_duplicate(ticket_id: int, title: str, body: str) -> Optional[int]:
    """
    Embeds the text and checks if it is semantically identical to a previous ticket.
    Returns the ID of the original ticket if it's a duplicate, else None.
    """
    text_to_embed = f"{title}\n{body}"
    query_vec = embed_fn.embed_query(text_to_embed)
    
    # Search for nearest neighbor
    results = dedup_collection.query(
        query_embeddings=[query_vec],
        n_results=1
    )
    
    # If we have a match and the cosine distance is < 0.1 (Highly similar / Near Identical)
    if results['ids'] and len(results['ids'][0]) > 0 and results['distances'][0][0] < 0.1:
        original_id = int(results['ids'][0][0])

        if original_id != ticket_id:
            return original_id
        
    # If not a duplicate, add it to the cache for future checks
    dedup_collection.upsert(
        ids=[str(ticket_id)],
        embeddings=[query_vec],
        documents=[text_to_embed]
    )
    return None

def process_single_issue(file_path: str):
    """
    Reads a raw JSON, extracts knowledge, and saves the result.
    """
    filename = os.path.basename(file_path)
    output_path = os.path.join(OUTPUT_DIR, filename)

    # 1. Idempotency Check (File level)
    if os.path.exists(output_path):
        print(f"⏩ Skipping {filename} (Already processed)")
        return

    # 2. Read Raw Data
    with open(file_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    # Skip if body is empty
    if not raw_data.get("body"):
        print(f"⚠️ Skipping {filename} (Empty body)")
        return

    # 3. Prepare Data
    title = raw_data.get("title", "")
    body = raw_data.get("body", "")
    author = raw_data.get("user", {}).get("login", "Unknown")
    ticket_id = raw_data.get("number")
    
    # Create the base TicketNode
    ticket_node = TicketNode(
        id=ticket_id,
        title=title,
        status=raw_data.get("state"),
        created_at=raw_data.get("created_at"),
        author_name=author,
        url=raw_data.get("html_url"),
        body_text=body,
        extracted_data=None, 
        extraction_version=EXTRACTION_VERSION,
        duplicate_of=None # Initialize duplicate flag
    )

    print(f"🔍 Processing Issue #{ticket_node.id}: {title[:40]}...")

    # PRE-PROCESSING SEMANTIC CHECK ---
    duplicate_original_id = check_semantic_duplicate(ticket_id, title, body)
    
    if duplicate_original_id:
        print(f"   👯 Semantic Duplicate Detected! (Matches Issue #{duplicate_original_id}) - Skipping LLM Extraction.")
        ticket_node.duplicate_of = duplicate_original_id
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ticket_node.model_dump_json(indent=2))
        return # Skip the LLM lifting!

    # 4. Run LLM Extraction (with retry logic)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            extraction_result = extraction_chain.invoke({
                "title": title,
                "author": author,
                "body": body
            })
            
            # --- POST-PROCESSING OFFSETS ---
            for relation in extraction_result.relations:
                if relation.evidence and body:
                    start_idx = body.find(relation.evidence)
                    if start_idx != -1:
                        relation.evidence_start = start_idx
                        relation.evidence_end = start_idx + len(relation.evidence)
                    else:
                        relation.evidence_start = None
                        relation.evidence_end = None
            
            # Attach result to our node
            ticket_node.extracted_data = extraction_result
            
            # 5. Save to Disk
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(ticket_node.model_dump_json(indent=2))
            
            print(f"   ✅ Saved to {output_path}")
            log_extraction(success=True)
            break # Success, exit retry loop

        except Exception as e:
            print(f"   ❌ Attempt {attempt+1} failed: {e}")
            log_extraction(success=False)
            if attempt < max_retries - 1:
                time.sleep(2) 
            else:
                print(f"  Failed to process {filename} after retries.")

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.json')]
    print(f" Starting extraction pipeline for {len(files)} files using Gemini...")

    for i, filename in enumerate(files):
        process_single_issue(os.path.join(INPUT_DIR, filename))
        time.sleep(0.5)

    print("\n🎉 Extraction Complete!")

if __name__ == "__main__":
    main()