import os
import chromadb
from neo4j import GraphDatabase
from langchain_google_genai import ChatGoogleGenerativeAI 
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("❌ GOOGLE_API_KEY is missing from .env!")

class GraphRAG:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        
        # THE FIX: Do not download the heavy AI model on startup!
        self._embedding_fn = None 
        
        self.chroma_client = chromadb.Client()
        self.collection = self.chroma_client.get_or_create_collection(
            name="entities", 
            metadata={"hnsw:space": "cosine"}
        )
        
        # Setup Gemini 
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=GOOGLE_API_KEY,
            temperature=0
        )

    @property
    def embedding_fn(self):
        if self._embedding_fn is None:
            print("⏳ Downloading HuggingFace Embedding Model...")
            self._embedding_fn = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        return self._embedding_fn

    def index_entities(self):
        """Syncs Neo4j Entities to ChromaDB."""
        print("🔄 Syncing Graph Nodes to Vector Index...")
        query = "MATCH (e:Entity) RETURN e.name AS name, e.description AS desc, e.type AS type"
        
        with self.driver.session() as session:
            result = session.run(query)
            entities = [record for record in result]
            
        if not entities:
            print("⚠️ No entities found in Graph. Run the loader first!")
            return

        ids = [e["name"] for e in entities]
        documents = [f"{e['name']}: {e['desc']}" for e in entities]
        metadatas = [{"type": e["type"]} for e in entities]
        
        # Embed and Upsert
        embeddings = self.embedding_fn.embed_documents(documents)
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        print(f"✅ Indexed {len(entities)} entities into Vector Store.")

    def retrieve_context(self, query: str) -> str:
        # Step A: Vector Search
        query_vec = self.embedding_fn.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=3
        )
        
        if not results['ids'] or not results['ids'][0]:
            return None

        top_entities = results['ids'][0]
        print(f"🔍 Found Entry Points: {top_entities}")

        # Step B: Graph Traversal 
        cypher_query = """
        MATCH (source:Entity)-[r]->(target:Entity)
        WHERE (source.name IN $entity_names OR target.name IN $entity_names)
          AND type(r) IN ['AFFECTS', 'USES', 'CAUSES', 'RELATED_TO']
          AND r.evidence_list IS NOT NULL
          
        // Unpack the arrays we created during deduplication
        UNWIND range(0, size(r.evidence_list)-1) AS idx
        MATCH (t:Ticket {id: r.ticket_ref_list[idx]})
        
        RETURN 
            t.id AS source_id,
            t.title AS title, 
            t.created_at AS created_at, 
            t.url AS url,
            r.evidence_list[idx] AS excerpt,
            r.offset_start_list[idx] AS offset_start,
            r.offset_end_list[idx] AS offset_end,
            type(r) AS relationship,
            source.name AS source_entity,
            target.name AS target_entity
        ORDER BY t.created_at DESC
        LIMIT 5
        """
        
        context_lines = []
        with self.driver.session() as session:
            result = session.run(cypher_query, entity_names=top_entities)
            for record in result:
                context_lines.append(
                    f"- Claim: [{record['source_entity']}] {record['relationship']} [{record['target_entity']}]\n"
                    f"  Source ID: Issue #{record['source_id']} ({record['url']})\n"
                    f"  Timestamp: {record['created_at']} | Offsets: [{record['offset_start']}:{record['offset_end']}]\n"
                    f"  Excerpt: \"{record['excerpt']}\""
                )
        
        return "\n\n".join(context_lines)

    def answer_question(self, user_query: str) -> str:
        # 1. Retrieve
        context = self.retrieve_context(user_query)
        
        print("\n" + "="*40)
        print(f" GRAPH CONTEXT RETRIEVED:\n{context}")
        print("="*40 + "\n")

        if not context:
            return "I couldn't find any relevant info in the database."

        # 2. Synthesize
        prompt = f"""
        You are an expert analytical AI querying a corporate Knowledge Graph.
        Your task is to answer the user's question using ONLY the provided CONTEXT.

        STRICT RULES:
        1. **Absolute Grounding**: Base every claim strictly on the context. If the answer is not in the context, say "I don't have enough information."
        2. **Cite Sources**: Always mention the Ticket Title and Date when stating a fact.
        3. **Handling Conflicts & Revisions**:
           - If multiple tickets make conflicting claims, look at their 'Date' to establish a chronological timeline. 
           - Present the evolution of the decision (e.g., "Initially in [Date], Ticket A stated X, but later in [Date], Ticket B stated Y").
           - Treat the most recent date as the current truth.
        4. **Ambiguity & Halting (CRITICAL)**: 
           - If the context presents fundamentally ambiguous or conflicting information that CANNOT be resolved chronologically (e.g., two tickets on the same day making opposite claims, or missing context to pick a winner), DO NOT GUESS.
           - Instead, HALT your synthesis. Explicitly state the exact conflict found in the sources, and ask the user a specific follow-up clarifying question to resolve the ambiguity.

        CONTEXT:
        {context}
        
        QUESTION: 
        {user_query}
        """
        
        print(f" Generating agentic answer using Gemini 2.5 Flash...")
        response = self.llm.invoke(prompt)
        return response.content

# Run it
rag_engine = GraphRAG()

if __name__ == "__main__":
    rag_engine.index_entities()
    print("\n Query: 'Tell me about CodeQL bugs'") 
    print(rag_engine.answer_question("Tell me about CodeQL bugs"))