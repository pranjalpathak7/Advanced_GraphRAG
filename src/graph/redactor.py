import os
import sys
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# Config
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

def apply_tombstone(ticket_id: int):
    """
    Applies the Tombstone pattern to a specific Ticket node.
    Scrubs all sensitive/raw text data but maintains the node and edges for topological integrity.
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    
    # The Cypher query to scrub the node
    tombstone_query = """
    MATCH (t:Ticket {id: $ticket_id})
    
    // 1. Scrub all sensitive properties and PII
    SET t.title = '[REDACTED FOR COMPLIANCE]',
        t.body_text = '[TEXT PURGED]',
        t.author = '[REDACTED]',
        t.url = 'https://redacted.local',
        t.status = 'REDACTED'
    
    // 2. We return the number of edges we saved from being orphaned
    WITH t
    MATCH (t)-[r:MENTIONS]->()
    RETURN count(r) AS preserved_edges
    """
    
    print(f"🚨 Initiating Redaction Protocol for Ticket #{ticket_id}...")
    
    with driver.session() as session:
        result = session.run(tombstone_query, ticket_id=ticket_id)
        record = result.single()
        
        if record is not None:
            preserved = record["preserved_edges"]
            print(f"✅ SUCCESS: Ticket #{ticket_id} has been permanently scrubbed.")
            print(f"🔗 Topological Integrity Maintained: {preserved} semantic edges were preserved.")
        else:
            print(f"⚠️ WARNING: Ticket #{ticket_id} was not found in the Knowledge Graph.")

    driver.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.graph.redactor <ticket_id>")
    else:
        try:
            target_id = int(sys.argv[1])
            apply_tombstone(target_id)
        except ValueError:
            print("❌ Error: Ticket ID must be an integer.")