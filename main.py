import argparse
import subprocess
import sys

def run_loader():
    print("📦 Starting Neo4j Graph Ingestion...")
    subprocess.run([sys.executable, "-m", "src.graph.loader"])

def run_resolution():
    print("🔍 Starting Entity Resolution (Deduplication)...")
    subprocess.run([sys.executable, "-m", "src.graph.resolution"])

def run_redaction(ticket_id: int):
    print(f"🛡️ Starting Redaction for Ticket {ticket_id}...")
    subprocess.run([sys.executable, "-m", "src.graph.redactor", str(ticket_id)])

def run_api():
    print(" Starting FastAPI Server on port 8000...")
    subprocess.run([sys.executable, "-m", "uvicorn", "src.api.server:app", "--reload"])

def run_ui():
    print("🎨 Starting Streamlit UI...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "src/ui/app.py"])

def print_help():
    print("""
🧠 Layer10 Memory Core - Execution Controller

Available Commands:
  python main.py --load              : Parses JSON files and loads them into Neo4j
  python main.py --resolve           : Runs the LLM-based Entity Deduplication
  python main.py --redact <id>       : Applies the Tombstone Pattern to a specific ticket
  python main.py --api               : Starts the FastAPI GraphRAG Backend
  python main.py --ui                : Starts the Streamlit Interactive Map
    """)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Layer10 Take-Home Controller")
    parser.add_argument("--load", action="store_true", help="Load data into Neo4j")
    parser.add_argument("--resolve", action="store_true", help="Run Entity Canonicalization")
    parser.add_argument("--redact", type=int, help="Apply Tombstone pattern to a Ticket ID", metavar="TICKET_ID")
    parser.add_argument("--api", action="store_true", help="Start FastAPI Server")
    parser.add_argument("--ui", action="store_true", help="Start Streamlit App")
    
    args = parser.parse_args()

    if not (args.load or args.resolve or args.redact or args.api or args.ui):
        print_help()
    else:
        if args.load:
            run_loader()
        if args.resolve:
            run_resolution()
        if args.redact:
            run_redaction(args.redact)
        if args.api:
            run_api()
        if args.ui:
            run_ui()