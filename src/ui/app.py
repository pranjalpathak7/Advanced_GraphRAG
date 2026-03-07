import os
import requests
import time
import streamlit as st
from neo4j import GraphDatabase
from streamlit_agraph import agraph, Node, Edge, Config
from dotenv import load_dotenv

# --- Configuration & Setup ---
load_dotenv()
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

st.set_page_config(page_title="Layer10 Memory Core", page_icon="🧠", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0b0f19; color: #e2e8f0; }
    
    /* Squash the massive empty space at the top of the sidebar */
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem;
    }
    
    .metric-card {
        background: linear-gradient(145deg, #161b22, #0d1117);
        padding: 12px 15px; /* Reduced vertical padding */
        border-radius: 12px;
        border-left: 4px solid #00f2fe;
        box-shadow: 0 4px 20px rgba(0, 242, 254, 0.15);
        margin-bottom: 12px; /* Reduced bottom margin */
    }
    .metric-card h2 { margin: 0; color: #fff; font-size: 2.2rem; } /* Slightly smaller number */
    .metric-card p { margin: 0; color: #8b949e; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; }
    
    .evidence-box {
        background-color: #161b22;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #30363d;
        border-left: 4px solid #f78166;
        margin-bottom: 15px;
        max-height: 400px;
        overflow-y: auto;
    }
    .claim-box {
        background-color: #0d1117;
        padding: 10px;
        border-radius: 6px;
        border: 1px solid #30363d;
        margin-bottom: 10px;
    }
    .alias-pill {
        display: inline-block;
        background: #30363d;
        padding: 4px 8px;
        border-radius: 12px;
        font-size: 0.8em;
        margin: 2px;
    }
</style>
""", unsafe_allow_html=True)

# --- Database Connection & Query Helpers ---
@st.cache_resource
def init_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

driver = init_driver()

def get_graph_metrics():
    with driver.session() as session:
        nodes = session.run("MATCH (n:Entity) RETURN count(n) as c").single()["c"]
        edges = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
    return nodes, edges

def get_orphan_ratio():
    query = """
    MATCH (e:Entity)
    OPTIONAL MATCH (e)-[r]-()
    WITH e, count(r) as degree
    WITH sum(CASE WHEN degree <= 1 THEN 1 ELSE 0 END) as orphans, count(e) as total
    RETURN orphans, total
    """
    with driver.session() as session:
        res = session.run(query).single()
        if not res or res["total"] == 0: return 0.0
        return round((res["orphans"] / res["total"]) * 100, 1)

def get_graph_topology(limit=200):
    query = """
    MATCH (t:Ticket)-[:MENTIONS]->(e:Entity)
    RETURN toString(t.id) AS ticket_id, t.status AS t_status,
           e.name AS entity_name, e.type AS e_type
    ORDER BY t.created_at DESC 
    LIMIT $limit
    """
    with driver.session() as session:
        return [record.data() for record in session.run(query, limit=limit)]

def get_ticket_details(ticket_id):
    query = """
    MATCH (t:Ticket {id: $id})
    RETURN t.title AS title, t.url AS url, t.status AS status, t.body_text AS body, t.created_at AS timestamp
    """
    with driver.session() as session:
        res = session.run(query, id=ticket_id).single()
        return res.data() if res else None

def get_entity_details(entity_name):
    query = """
    MATCH (e:Entity {name: $name})
    OPTIONAL MATCH (alias:Entity)-[:ALIAS_OF]->(e)
    RETURN e.name AS name, e.type AS type, e.description AS desc, collect(alias.name) AS aliases
    """
    with driver.session() as session:
        res = session.run(query, name=entity_name).single()
        return res.data() if res else None

def get_entity_claims(entity_name):
    query = """
    MATCH (source:Entity)-[r]->(target:Entity)
    WHERE (source.name = $name OR target.name = $name) 
      AND type(r) IN ['AFFECTS', 'USES', 'CAUSES', 'RELATED_TO']
      AND r.evidence_list IS NOT NULL
    
    UNWIND range(0, size(r.evidence_list)-1) AS idx
    MATCH (t:Ticket {id: r.ticket_ref_list[idx]})
    
    RETURN source.name AS source, type(r) AS relationship, target.name AS target,
           t.id AS ticket_id, t.created_at AS timestamp, t.url AS url,
           r.evidence_list[idx] AS excerpt, 
           r.offset_start_list[idx] AS offset_start, 
           r.offset_end_list[idx] AS offset_end
    """
    with driver.session() as session:
        return [record.data() for record in session.run(query, name=entity_name)]


# --- UI LAYOUT: SIDEBAR (Observability) ---
with st.sidebar:
    st.markdown("### 🧠 Layer10 Memory") # Replaced st.title to save vertical space
    st.caption("v2.0 - Grounded Extraction Engine")
    st.divider()
    
    st.markdown("#### 📊 System Observability")
    try:
        n_count, e_count = get_graph_metrics()
        orphan_pct = get_orphan_ratio()
        
        telemetry_resp = requests.get(f"{API_URL}/telemetry")
        telemetry = telemetry_resp.json() if telemetry_resp.status_code == 200 else {}
        
        succ = telemetry.get('extraction_successes', 0)
        fail = telemetry.get('extraction_failures', 0)
        fail_rate = round((fail / (succ + fail) * 100), 1) if (succ + fail) > 0 else 0.0
        
        up = telemetry.get('rag_thumbs_up', 0)
        down = telemetry.get('rag_thumbs_down', 0)
        satisfaction = round((up / (up + down) * 100), 1) if (up + down) > 0 else 0.0

        st.markdown(f"<div class='metric-card'><p>Total Entities</p><h2>{n_count}</h2></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-card'><p>Graph Orphan Ratio</p><h2>{orphan_pct}%</h2><p>Target: < 20%</p></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-card'><p>Extraction Failure Rate</p><h2>{fail_rate}%</h2><p>Pydantic Validation</p></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-card'><p>RAG Satisfaction</p><h2>{satisfaction}%</h2><p>{up} 👍 / {down} 👎</p></div>", unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"Telemetry Offline: Ensure FastAPI is running.")

# --- UI LAYOUT: MAIN PAGE ---
st.title("🧠 Layer10 Graph Memory")
st.caption("Grounded Long-Term Memory via Structured Extraction")

try:
    topology_data = get_graph_topology(limit=200)
except Exception as e:
    st.error(f"Failed to fetch data from Neo4j: {e}")
    topology_data = []

tab_explore, tab_query = st.tabs(["🌐 Memory Explorer", "🤖 GraphRAG Agent"])

with tab_explore:
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        entity_types = list(set([row.get('e_type', 'Unknown') for row in topology_data]))
        selected_type = st.selectbox("Filter by Entity Type:", ["All"] + entity_types)
    with col_f2:
        ticket_statuses = list(set([row.get('t_status', 'Unknown') for row in topology_data]))
        selected_status = st.selectbox("Filter by Ticket Status:", ["All"] + ticket_statuses)

    st.info("💡 **PRO TIP:** Use your **Mouse Wheel** to zoom in/out, and click any node to instantly view its Grounded Evidence Panel.")

    col_graph, col_panel = st.columns([2, 1])
    
    with col_graph:
        nodes, edges, added_nodes = [], [], set()

        for row in topology_data:
            t_node_id = str(row['ticket_id'])
            e_node_id = str(row['entity_name'])
            
            if selected_type != "All" and row.get('e_type') != selected_type: continue
            if selected_status != "All" and row.get('t_status') != selected_status: continue

            if t_node_id not in added_nodes:
                nodes.append(Node(id=t_node_id, label=f"Issue #{t_node_id}", size=25, shape="hexagon", color="#1f6feb"))
                added_nodes.add(t_node_id)

            if e_node_id not in added_nodes:
                color_map = {"Technology": "#d2a8ff", "Problem": "#f85149", "Feature": "#3fb950", "Organization": "#a5d6ff"}
                nodes.append(Node(id=e_node_id, label=e_node_id, size=20, shape="dot", color=color_map.get(row.get('e_type'), "#8b949e")))
                added_nodes.add(e_node_id)

            edges.append(Edge(source=t_node_id, target=e_node_id, color="#6e7681"))

        if nodes:
            config = Config(
                width=800, height=750, directed=False, physics=True, hierarchical=False,
                nodeHighlightBehavior=True, highlightColor="#00f2fe", collapsible=False,
                kwargs={"physics": {"solver": "forceAtlas2Based", "forceAtlas2Based": {"springLength": 200, "springConstant": 0.05, "damping": 0.4}}}
            )
            clicked_node = agraph(nodes=nodes, edges=edges, config=config)
        else:
            st.warning("No nodes match the selected filters.")
            clicked_node = None

    with col_panel:
        st.subheader("🔎 Evidence Panel")
        if clicked_node:
            if clicked_node.isdigit():
                real_id = int(clicked_node)
                t_details = get_ticket_details(real_id)
                if t_details:
                    st.markdown(f"### Issue #{real_id}")
                    st.markdown(f"**Title:** {t_details['title']}")
                    st.markdown(f"**Status:** `{t_details['status']}` | **Date:** `{t_details['timestamp']}`")
                    st.markdown(f"[🔗 View Original Source]({t_details['url']})")
                    st.markdown("#### Grounding Excerpt:")
                    body_preview = (t_details['body'][:800] + '...') if t_details['body'] else "No excerpt available."
                    st.markdown(f"<div class='evidence-box'>{body_preview}</div>", unsafe_allow_html=True)
            else:
                real_name = clicked_node
                e_details = get_entity_details(real_name)
                claims = get_entity_claims(real_name)
                if e_details:
                    st.markdown(f"### Entity: {e_details['name']}")
                    st.markdown(f"**Type:** `{e_details['type']}`")
                    st.markdown(f"**Description:** {e_details['desc']}")
                    
                    st.markdown("#### Canonical Merges:")
                    if e_details.get('aliases') and e_details['aliases'][0] is not None:
                        for alias in e_details['aliases']:
                            st.markdown(f"<span class='alias-pill'>{alias}</span>", unsafe_allow_html=True)
                    else:
                        st.caption("No duplicate aliases merged into this entity.")
                    
                    st.markdown("#### Semantic Claims & Evidence:")
                    if claims:
                        for c in claims:
                            st.markdown(f"<div class='claim-box'>"
                                        f"<b>{c['source']}</b> <code>{c['relationship']}</code> <b>{c['target']}</b><br/>"
                                        f"<small><b>Source ID:</b> <a href='{c['url']}'>Issue #{c['ticket_id']}</a> | <b>Date:</b> {c['timestamp']}</small><br/>"
                                        f"<small><b>Offsets:</b> [{c['offset_start']} : {c['offset_end']}]</small><br/><br/>"
                                        f"<i>\"{c['excerpt']}\"</i>"
                                        f"</div>", unsafe_allow_html=True)
                    else:
                        st.caption("No semantic claims found.")
        else:
            st.caption("Click any node on the graph to instantly view its supporting evidence, canonical merges, and metadata.")

# --- CONSOLIDATED RAG TAB  ---
with tab_query:
    st.markdown("### 💬 Ask the Memory Graph")
    
    if "rag_answer" not in st.session_state:
        st.session_state.rag_answer = None
        st.session_state.rag_context = None

    question = st.text_input("Enter your query:", placeholder="e.g., What bugs were fixed in CodeQL?")
    
    if st.button("Synthesize Answer", type="primary"):
        if question:
            with st.spinner("Traversing Knowledge Graph..."):

                st.session_state.rag_answer = None
                st.session_state.rag_context = None

                try:
                    resp = requests.post(f"{API_URL}/query", json={"question": question})
                    if resp.status_code == 200:
                        data = resp.json()
                        st.session_state.rag_answer = data["answer"]
                        st.session_state.rag_context = data["context_used"]
                    else:
                        st.error(f"API Error: {resp.status_code}")
                except Exception as e:
                    st.error("Ensure FastAPI server is running (`python main.py --api`).")

    # Render the answer OUTSIDE the button's if-block
    if st.session_state.rag_answer:
        st.markdown("#### 💡 AI Synthesis")
        st.write(st.session_state.rag_answer)
        st.markdown("#### 🔗 Grounding Context")
        st.info(st.session_state.rag_context)
        
        st.markdown("---")
        st.write("Was this memory retrieval accurate?")
        col1, col2, _ = st.columns([1, 1, 8])
        with col1:
            if st.button("👍 Yes"):
                requests.post(f"{API_URL}/feedback", json={"is_positive": True})
                st.success("Feedback logged! Thank you.")
                time.sleep(1)
                st.session_state.rag_answer = None # Reset the form
                st.rerun() 
        with col2:
            if st.button("👎 No"):
                requests.post(f"{API_URL}/feedback", json={"is_positive": False})
                st.error("Feedback logged! We will review this.")
                time.sleep(1)
                st.session_state.rag_answer = None # Reset the form
                st.rerun()