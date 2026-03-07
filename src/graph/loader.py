import os
import json
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# Configuration
EXTRACTED_DIR = "data/extracted"
URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")

class GraphLoader:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.verify_connection()

    def verify_connection(self):
        try:
            self.driver.verify_connectivity()
            print("✅ Connected to Neo4j!")
        except Exception as e:
            print(f"❌ Failed to connect to Neo4j: {e}")
            raise

    def close(self):
        self.driver.close()

    def create_constraints(self):
        """
        Creates Unique Constraints. 
        """
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Ticket) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE"
        ]
        with self.driver.session() as session:
            for q in queries:
                session.run(q)
        print("🔒 Schema constraints applied.")

    def load_issue(self, data: dict):
        """
        The Master Query.
        """
        #  Handle Semantic Duplicates ---
        duplicate_of = data.get("duplicate_of")
        if duplicate_of:
            dup_query = """
            MERGE (t:Ticket {id: $ticket_id})
            SET t.title = $title,
                t.status = $status,
                t.url = $url,
                t.created_at = $created_at,
                t.author = $author,
                t.body_text = $body,
                t.extraction_version = $extraction_version
            
            // Connect this ticket to the original ticket it duplicates
            MERGE (orig:Ticket {id: $duplicate_of})
            MERGE (t)-[:DUPLICATE_OF]->(orig)
            """
            params = {
                "ticket_id": data.get("id"),
                "title": data.get("title"),
                "status": data.get("status"),
                "url": data.get("url"),
                "created_at": data.get("created_at"),
                "author": data.get("author_name"),
                "body": data.get("body_text"), 
                "extraction_version": data.get("extraction_version", "unknown"),
                "duplicate_of": duplicate_of
            }
            with self.driver.session() as session:
                session.run(dup_query, params)
            return # Skip entity processing, as it's a duplicate!


        # --- Normal Ticket Processing ---
        query = """
        MERGE (t:Ticket {id: $ticket_id})
        SET t.title = $title,
            t.status = $status,
            t.url = $url,
            t.created_at = $created_at,
            t.author = $author,
            t.body_text = $body,
            t.extraction_version = $extraction_version 

        WITH t
        UNWIND $entities AS entity_data
        
        MERGE (e:Entity {name: entity_data.name})
        ON CREATE SET e.type = entity_data.type, e.description = entity_data.description
        
        MERGE (t)-[m:MENTIONS]->(e)
        """

        extracted = data.get("extracted_data", {})
        if not extracted: 
            return 

        params = {
            "ticket_id": data.get("id"),
            "title": data.get("title"),
            "status": data.get("status"),
            "url": data.get("url"),
            "created_at": data.get("created_at"),
            "author": data.get("author_name"),
            "body": data.get("body_text"), 
            "extraction_version": data.get("extraction_version", "unknown"),
            "entities": [e for e in extracted.get("entities", [])]
        }

        with self.driver.session() as session:
            session.run(query, params)
            
            # --- CLAIM DEDUP (LOSSLESS EVIDENCE MERGING) ---
            relations = extracted.get("relations", [])
            for rel in relations:
                rel_query = """
                MATCH (source:Entity {name: $source_name})
                MATCH (target:Entity {name: $target_name})
                MERGE (source)-[r:%s]->(target)
                
                // If this is the FIRST time this claim is made, initialize arrays
                ON CREATE SET 
                    r.evidence_list = [$evidence],
                    r.ticket_ref_list = [$ticket_id],
                    r.offset_start_list = [$offset_start],
                    r.offset_end_list = [$offset_end]
                
                // If this claim ALREADY exists, append the new evidence to the arrays safely
                ON MATCH SET 
                    r.evidence_list = coalesce(r.evidence_list, []) + [$evidence],
                    r.ticket_ref_list = coalesce(r.ticket_ref_list, []) + [$ticket_id],
                    r.offset_start_list = coalesce(r.offset_start_list, []) + [$offset_start],
                    r.offset_end_list = coalesce(r.offset_end_list, []) + [$offset_end]
                """ % rel['label'] 
                
                session.run(rel_query, {
                    "source_name": rel['source'],
                    "target_name": rel['target'],
                    "evidence": rel['evidence'],
                    "ticket_id": data.get("id"),
                    "offset_start": rel.get('evidence_start') if rel.get('evidence_start') is not None else -1,
                    "offset_end": rel.get('evidence_end') if rel.get('evidence_end') is not None else -1      
                })

def main():
    loader = GraphLoader(URI, USER, PASSWORD)
    loader.create_constraints()

    files = [f for f in os.listdir(EXTRACTED_DIR) if f.endswith(".json")]
    print(f"📦 Updating {len(files)} files in Graph (Adding body text)...")

    for filename in files:
        filepath = os.path.join(EXTRACTED_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            loader.load_issue(data)
            print(f"   Updated: {filename}")

    loader.close()
    print("🎉 Graph Update Complete!")

if __name__ == "__main__":
    main()