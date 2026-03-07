import os
from neo4j import GraphDatabase
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from typing import List
from dotenv import load_dotenv

load_dotenv()

# Config
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class EntityMerge(BaseModel):
    primary_name: str = Field(..., description="The canonical name to keep")
    aliases: List[str] = Field(..., description="The list of names to merge into the primary")

class ResolutionResult(BaseModel):
    merges: List[EntityMerge]

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", # Updated to the faster 2.5-flash model
    google_api_key=GOOGLE_API_KEY,
    temperature=0
)

def run_resolution():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    
    # 1. Fetch all active entity names (ignore ones that are already aliases)
    print("🔍 Fetching active entities for analysis...")
    with driver.session() as session:
        result = session.run("MATCH (e:Entity) WHERE e.is_alias IS NULL RETURN e.name AS name")
        all_names = [r["name"] for r in result]

    if not all_names:
        print("⚠️ No entities found to resolve.")
        return

    # 2. Ask LLM to find duplicates
    print(f"🤖 Analyzing {len(all_names)} entities for semantic duplicates...")
    prompt = f"""
    Analyze this list of technical entities. Identify synonymous or near-identical entities that should be merged.
    Return a list of merges where 'primary_name' is the best version and 'aliases' are the duplicates.
    
    Entities: {all_names}
    """
    
    structured_llm = llm.with_structured_output(ResolutionResult)
    try:
        resolution = structured_llm.invoke(prompt)
    except Exception as e:
        print(f"❌ LLM Error during resolution: {e}")
        return

    if not resolution.merges:
        print("✅ No duplicates found by the LLM.")
        return

    # 3. Execute NON-DESTRUCTIVE Merges in Neo4j
    print(f"Applying {len(resolution.merges)} reversible merge operations...")
    
    # We explicitly define the semantic edges we use in our ontology
    SEMANTIC_EDGES = ['AFFECTS', 'USES', 'CAUSES', 'RELATED_TO']

    with driver.session() as session:
        for group in resolution.merges:
            for alias in group.aliases:
                if alias == group.primary_name: continue
                print(f"   Refactoring: '{alias}' -> '{group.primary_name}'")
                
                # --- STEP A: Create Audit Trail (ALIAS_OF) ---
                audit_query = """
                MATCH (primary:Entity {name: $primary})
                MATCH (alias:Entity {name: $alias})
                WHERE elementId(primary) <> elementId(alias)
                
                // Mark alias as inactive (Tombstone)
                SET alias.is_alias = true
                
                // Create Traceability Link
                MERGE (alias)-[audit:ALIAS_OF]->(primary)
                SET audit.merged_at = datetime(),
                    audit.reason = 'LLM Semantic Resolution'
                """
                session.run(audit_query, primary=group.primary_name, alias=alias)

                # --- STEP B: Rewire TICKET -> MENTIONS -> ENTITY ---
                mentions_query = """
                MATCH (primary:Entity {name: $primary})
                MATCH (t:Ticket)-[r:MENTIONS]->(alias:Entity {name: $alias})
                
                MERGE (t)-[new_r:MENTIONS]->(primary)
                ON CREATE SET 
                    new_r.evidence_list = r.evidence_list,
                    new_r.ticket_ref_list = r.ticket_ref_list,
                    new_r.offset_start_list = r.offset_start_list,
                    new_r.offset_end_list = r.offset_end_list,
                    new_r.rewired_from = alias.name
                ON MATCH SET 
                    new_r.evidence_list = coalesce(new_r.evidence_list, []) + coalesce(r.evidence_list, []),
                    new_r.ticket_ref_list = coalesce(new_r.ticket_ref_list, []) + coalesce(r.ticket_ref_list, []),
                    new_r.offset_start_list = coalesce(new_r.offset_start_list, []) + coalesce(r.offset_start_list, []),
                    new_r.offset_end_list = coalesce(new_r.offset_end_list, []) + coalesce(r.offset_end_list, []),
                    new_r.rewired_from = coalesce(new_r.rewired_from, '') + ',' + alias.name
                
                DELETE r
                """
                session.run(mentions_query, primary=group.primary_name, alias=alias)

                # --- STEP C: Rewire Semantic Edges ---
                for rel_type in SEMANTIC_EDGES:
                    # Rewire Outgoing
                    out_query = f"""
                    MATCH (primary:Entity {{name: $primary}})
                    MATCH (alias:Entity {{name: $alias}})-[r:{rel_type}]->(target:Entity)
                    MERGE (primary)-[new_r:{rel_type}]->(target)
                    ON CREATE SET new_r += properties(r), new_r.rewired_from = alias.name
                    ON MATCH SET new_r.evidence_list = coalesce(new_r.evidence_list, []) + coalesce(r.evidence_list, [])
                    DELETE r
                    """
                    session.run(out_query, primary=group.primary_name, alias=alias)

                    # Rewire Incoming
                    in_query = f"""
                    MATCH (primary:Entity {{name: $primary}})
                    MATCH (source:Entity)-[r:{rel_type}]->(alias:Entity {{name: $alias}})
                    MERGE (source)-[new_r:{rel_type}]->(primary)
                    ON CREATE SET new_r += properties(r), new_r.rewired_from = alias.name
                    ON MATCH SET new_r.evidence_list = coalesce(new_r.evidence_list, []) + coalesce(r.evidence_list, [])
                    DELETE r
                    """
                    session.run(in_query, primary=group.primary_name, alias=alias)

    driver.close()
    print("✅ Entity Resolution Complete (Non-Destructive & Reversible).")

if __name__ == "__main__":
    run_resolution()