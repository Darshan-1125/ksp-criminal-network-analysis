import os
import json
import logging
import re
import numpy as np
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage

from app.db import SessionLocal, DATABASE_URL
from app.models import FIRCase, Accused, Location, District, PoliceStation, CaseEmbedding
from app.services.db_service import (
    search_cases_structured,
    get_case_by_id,
    get_network_for_entity,
    serialize_case
)
from app.services.rag_service import synthesize_answer

logger = logging.getLogger(__name__)

# Global in-memory memory for the hackathon
SESSION_MEMORY = {}  # session_id -> {"last_fir_number": str, "last_accused_id": int}

class AgentState(TypedDict):
    message: str
    language: str
    session_id: str
    classification: str  # structured | semantic | graph | hybrid
    filters: Dict[str, Any]
    entity: Dict[str, Any]  # {"type": "accused"|"location"|None, "query": str|None, "id": int|None}
    is_trend: bool
    retrieved_cases: List[Dict[str, Any]]
    retrieved_graph: Optional[Dict[str, Any]]
    answer: str
    citations: List[Dict[str, Any]]
    visual_type: str  # network | trend | none
    visual_payload: Optional[Dict[str, Any]]

def get_session_context(session_id: str) -> str:
    """Helper to format previous session context for the LLM."""
    if not session_id or session_id not in SESSION_MEMORY:
        return ""
    mem = SESSION_MEMORY[session_id]
    context = []
    if mem.get("last_fir_number"):
        context.append(f"Last mentioned FIR: {mem.get('last_fir_number')}")
    if mem.get("last_accused_id"):
        context.append(f"Last mentioned Accused ID: {mem.get('last_accused_id')}")
    return "\n".join(context)

def heuristic_classify_and_extract(message: str, session_id: str = None) -> dict:
    """Perform rule-based classification and extraction as a fallback or pre-pass."""
    msg_lower = message.lower()
    
    # 1. District heuristic
    districts = [
        "mysuru", "mysore", "bengaluru", "bangalore", "belagavi", "belgaum", 
        "hubballi", "hubli", "dharwad", "mangaluru", "mangalore", "mandya", 
        "kolar", "udupi", "tumakuru", "tumkur", "bidar", "kalaburagi", "gulbarga", 
        "yadgir", "chamarajanagar", "koppal", "haveri", "gadag", "bagalkot", 
        "vijayapura", "bijapur", "chitradurga", "davanagere", "shivamogga", "shimoga", 
        "ramanagara", "chikkaballapur", "ballari", "bellary", "chamarajanagara"
    ]
    found_district = None
    for d in districts:
        if d in msg_lower:
            found_district = d.capitalize()
            if found_district == "Mysore":
                found_district = "Mysuru"
            elif found_district == "Bangalore":
                found_district = "Bengaluru"
            break
            
    # 2. Crime type heuristic
    crime_types = ["robbery", "theft", "murder", "assault", "cybercrime", "extortion", "burglary", "kidnapping", "drug", "narcotics", "fraud", "homicide", "cheating", "riot"]
    found_crime = None
    for c in crime_types:
        if c in msg_lower:
            found_crime = c.capitalize()
            break

    # 3. Dates heuristic
    date_matches = re.findall(r'\d{4}-\d{2}-\d{2}', message)
    date_from = date_matches[0] if len(date_matches) > 0 else None
    date_to = date_matches[1] if len(date_matches) > 1 else None
    
    year_match = re.search(r'\b(20\d{2})\b', message)
    if year_match and not date_from:
        year = year_match.group(1)
        date_from = f"{year}-01-01"
        date_to = f"{year}-12-31"

    # 4. Graph keywords heuristic
    graph_keywords = ["network", "connected", "connection", "link", "associate", "accomplice", "contacts", "relation", "relate", "friends", "graph"]
    is_graph = any(kw in msg_lower for kw in graph_keywords)
    
    # 5. Semantic keywords heuristic
    semantic_keywords = ["similar", "mo of", "like case", "narrative like", "pattern like", "similar cases", "modus operandi", "describe", "narration"]
    is_semantic = any(kw in msg_lower for kw in semantic_keywords)
    
    # 6. Trend keywords heuristic
    trend_keywords = ["trend", "count", "number of", "how many", "statistics", "compare", "aggregation", "percentage"]
    is_trend = any(kw in msg_lower for kw in trend_keywords)

    classification = "structured"
    if is_graph:
        classification = "graph"
    elif is_semantic:
        if found_district or found_crime or date_from:
            classification = "hybrid"
        else:
            classification = "semantic"
            
    # 7. Accused name extraction
    accused_name = None
    accused_match = re.search(r'(?:accused|suspect)\s+([A-Za-z]+(?:\s+[A-Za-z]\.)?)', message, re.IGNORECASE)
    if accused_match:
        accused_name = accused_match.group(1).strip()
        
    # Apply session memory if needed
    last_accused_id = None
    last_fir = None
    if session_id and session_id in SESSION_MEMORY:
        last_accused_id = SESSION_MEMORY[session_id].get("last_accused_id")
        last_fir = SESSION_MEMORY[session_id].get("last_fir_number")
        
        # If user asks "what about his other cases?"
        if any(pronoun in msg_lower for pronoun in ["his ", "her ", "he ", "she ", "him ", "this accused"]) and last_accused_id and not accused_name:
            accused_name = f"Accused ID {last_accused_id}" # Will resolve in DB search

    return {
        "classification": classification,
        "filters": {
            "crime_type": found_crime,
            "district": found_district,
            "date_from": date_from,
            "date_to": date_to,
            "accused_name": accused_name if not accused_name or not accused_name.startswith("Accused ID") else None
        },
        "entity": {
            "type": "accused" if is_graph else None,
            "query": accused_name,
            "id": last_accused_id if accused_name and accused_name.startswith("Accused ID") else None
        },
        "is_trend": is_trend
    }

def llm_classify_and_extract(message: str, session_id: str = None) -> dict:
    """Use ChatGPT to classify the intent and extract structured filters/entities."""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        return heuristic_classify_and_extract(message, session_id)
        
    session_context = get_session_context(session_id)
    
    system_prompt = (
        "You are an AI router for Karnataka Crime GPT.\n"
        "Your task is to classify the user's message and extract query filters and entities.\n\n"
        "Classifications:\n"
        "- `graph`: if the user is asking about network, connections, accomplices, links between accused, or location connections.\n"
        "- `semantic`: if the user is looking for cases based on textual descriptions, MO patterns, narrative similarities, or 'similar to FIR X'.\n"
        "- `structured`: if the user is filtering cases by specific fields like district name, crime type, dates, status, or accused name, with NO semantic/graph query.\n"
        "- `hybrid`: if the query combines both structured filters (e.g. Mysuru district) and semantic similarity (e.g. similar to FIR X).\n\n"
        "You must output a JSON object with these EXACT keys:\n"
        "{\n"
        "  \"classification\": \"structured\" | \"semantic\" | \"graph\" | \"hybrid\",\n"
        "  \"filters\": {\n"
        "    \"crime_type\": \"string or null\",\n"
        "    \"district\": \"string or null\",\n"
        "    \"date_from\": \"YYYY-MM-DD or null\",\n"
        "    \"date_to\": \"YYYY-MM-DD or null\",\n"
        "    \"accused_name\": \"string or null\"\n"
        "  },\n"
        "  \"entity\": {\n"
        "    \"type\": \"accused\" | \"location\" | null,\n"
        "    \"query\": \"string or null\" (name of the accused or location details to search/graph)\n"
        "  },\n"
        "  \"is_trend\": true | false (true if they are asking for trends, statistics, counts, comparisons, or monthly graphs)\n"
        "}\n\n"
        f"Session Memory Context:\n{session_context or 'None'}\n"
        "Use the Session Memory Context to resolve pronouns (e.g. 'his cases' refers to the last mentioned Accused ID or name)."
    )

    try:
        chat = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.0,
            openai_api_key=openai_api_key,
            max_retries=1
        )
        response = chat.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=message)
        ])
        
        # Clean JSON markdown if present
        clean_content = response.content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        clean_content = clean_content.strip()
        
        parsed = json.loads(clean_content)
        # Ensure entity gets an 'id' key if we resolved it using memory
        entity = parsed.get("entity", {})
        entity["id"] = None
        
        # Resolve pronoun using memory
        if session_id and session_id in SESSION_MEMORY:
            mem = SESSION_MEMORY[session_id]
            if entity.get("type") == "accused" and not entity.get("query") and mem.get("last_accused_id"):
                entity["id"] = mem.get("last_accused_id")
            elif parsed.get("classification") == "graph" and not entity.get("type") and mem.get("last_accused_id"):
                entity["type"] = "accused"
                entity["id"] = mem.get("last_accused_id")
                
        parsed["entity"] = entity
        return parsed
    except Exception as e:
        logger.error(f"OpenAI Router API failed: {e}. Falling back to heuristics.")
        return heuristic_classify_and_extract(message, session_id)

# ----------------- Database / pgvector Helpers -----------------

def perform_vector_search(db, query_embedding: list, k: int = 5) -> list:
    """Performs pgvector cosine similarity search or SQLite fallback numpy cosine similarity."""
    if DATABASE_URL.startswith("postgresql"):
        try:
            results = db.query(CaseEmbedding.case_id).order_by(
                CaseEmbedding.embedding.cosine_distance(query_embedding)
            ).limit(k).all()
            return [r[0] for r in results]
        except Exception as e:
            logger.error(f"PostgreSQL pgvector search failed: {e}. Falling back to text matching.")
            return []
    else:
        # SQLite / standard fallback using numpy
        all_embeddings = db.query(CaseEmbedding).all()
        if not all_embeddings:
            return []
            
        matches = []
        q_vec = np.array(query_embedding)
        
        for emb in all_embeddings:
            if not emb.embedding:
                continue
            
            vec = emb.embedding
            if isinstance(vec, str):
                try:
                    vec = json.loads(vec)
                except:
                    continue
            
            if not isinstance(vec, list):
                continue
                
            a = np.array(vec)
            if a.shape != q_vec.shape:
                continue
                
            dot_product = np.dot(a, q_vec)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(q_vec)
            sim = dot_product / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0
            
            matches.append((emb.case_id, sim))
            
        matches.sort(key=lambda x: x[1], reverse=True)
        return [m[0] for m in matches[:k]]

def compute_trend_payload(filters: dict, db, group_by: str = "district") -> dict:
    """Helper to query cases and return data grouped by district, crime_type, or month matching trend shape."""
    from sqlalchemy import func
    try:
        # Base query depends on group_by
        if group_by == "district":
            query = db.query(District.name, func.count(FIRCase.id)).join(FIRCase, FIRCase.district_id == District.id)
            group_field = District.name
        elif group_by == "crime_type":
            query = db.query(FIRCase.crime_type, func.count(FIRCase.id))
            group_field = FIRCase.crime_type
        elif group_by == "month":
            from app.db import DATABASE_URL
            if DATABASE_URL.startswith("postgresql"):
                month_expr = func.to_char(FIRCase.date_reported, "YYYY-MM")
            else:
                month_expr = func.strftime("%Y-%m", FIRCase.date_reported)
            query = db.query(month_expr, func.count(FIRCase.id))
            group_field = month_expr
        else:
            group_by = "district"
            query = db.query(District.name, func.count(FIRCase.id)).join(FIRCase, FIRCase.district_id == District.id)
            group_field = District.name

        # Apply general filters
        if filters.get("district"):
            # Join District if it's not already joined
            if group_by != "district":
                query = query.join(District, FIRCase.district_id == District.id)
            query = query.filter(District.name.ilike(f"%{filters['district']}%"))

        if filters.get("crime_type"):
            query = query.filter(FIRCase.crime_type.ilike(f"%{filters['crime_type']}%"))
            
        if filters.get("date_from"):
            query = query.filter(FIRCase.date_reported >= filters["date_from"])
            
        if filters.get("date_to"):
            query = query.filter(FIRCase.date_reported <= filters["date_to"])

        # Order by key for month/crime_type/district
        if group_by == "month":
            data = query.group_by(group_field).order_by(group_field.asc()).all()
        else:
            data = query.group_by(group_field).order_by(func.count(FIRCase.id).desc()).all()
            
        return {
            "group_by": group_by,
            "data": [{"key": row[0], "count": row[1]} for row in data]
        }
    except Exception as e:
        logger.error(f"Failed to compute trend payload: {e}")
        return {"group_by": group_by, "data": []}

# ----------------- LangGraph Nodes -----------------

def classify_node(state: AgentState) -> dict:
    """Node that classifies the query and extracts filters."""
    result = llm_classify_and_extract(state["message"], state["session_id"])
    return {
        "classification": result.get("classification", "structured"),
        "filters": result.get("filters", {}),
        "entity": result.get("entity", {}),
        "is_trend": result.get("is_trend", False)
    }

def structured_search_node(state: AgentState) -> dict:
    """Node that performs structured case search."""
    cases = search_cases_structured(state["filters"])
    return {"retrieved_cases": cases}

def semantic_search_node(state: AgentState) -> dict:
    """Node that performs semantic embedding-based search."""
    message = state["message"]
    openai_api_key = os.getenv("OPENAI_API_KEY")
    retrieved_cases = []
    
    # Check if user asked for a specific case's similarity
    # e.g., "similar to FIR KA-2024-1123"
    fir_match = re.search(r'FIR\s+([A-Za-z0-9\-]+)', message, re.IGNORECASE)
    db = SessionLocal()
    try:
        query_text = message
        if fir_match:
            fir_num = fir_match.group(1)
            # Find the original case text
            source_case = db.query(FIRCase).filter(FIRCase.fir_number == fir_num).first()
            if source_case and source_case.narrative:
                query_text = source_case.narrative
                
        # Embed and search
        if openai_api_key:
            try:
                embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
                vector = embeddings.embed_query(query_text)
                case_ids = perform_vector_search(db, vector, k=5)
                for cid in case_ids:
                    case = db.query(FIRCase).filter(FIRCase.id == cid).first()
                    if case:
                        retrieved_cases.append(serialize_case(case, include_narrative=True))
            except Exception as e:
                logger.error(f"Semantic search embedding failed: {e}")
                # Fallback: simple text search on message
                fallback_cases = db.query(FIRCase).filter(
                    or_(
                        FIRCase.narrative.ilike(f"%{message}%"),
                        FIRCase.mo_description.ilike(f"%{message}%")
                    )
                ).limit(5).all()
                retrieved_cases = [serialize_case(c, include_narrative=True) for c in fallback_cases]
        else:
            # Fallback when key is missing: text match
            fallback_cases = db.query(FIRCase).filter(
                or_(
                    FIRCase.narrative.ilike(f"%{message}%"),
                    FIRCase.mo_description.ilike(f"%{message}%")
                )
            ).limit(5).all()
            retrieved_cases = [serialize_case(c, include_narrative=True) for c in fallback_cases]
            
    finally:
        db.close()
        
    return {"retrieved_cases": retrieved_cases}

def graph_search_node(state: AgentState) -> dict:
    """Node that performs network graph searches."""
    entity = state["entity"]
    db = SessionLocal()
    graph_payload = {"nodes": [], "edges": []}
    retrieved_cases = []
    
    try:
        resolved_type = entity.get("type")
        resolved_id = entity.get("id")
        query_str = entity.get("query")
        
        # 1. Resolve entity if not already resolved by ID
        if not resolved_id and query_str:
            if resolved_type == "accused":
                # Look up accused by name
                acc = db.query(Accused).filter(Accused.name.ilike(f"%{query_str}%")).first()
                if acc:
                    resolved_id = acc.id
            elif resolved_type == "location":
                loc = db.query(Location).filter(
                    or_(
                        Location.address.ilike(f"%{query_str}%"),
                        Location.city.ilike(f"%{query_str}%")
                    )
                ).first()
                if loc:
                    resolved_id = loc.id
            else:
                # Ambiguous: try accused then location
                acc = db.query(Accused).filter(Accused.name.ilike(f"%{query_str}%")).first()
                if acc:
                    resolved_type = "accused"
                    resolved_id = acc.id
                else:
                    loc = db.query(Location).filter(
                        or_(
                            Location.address.ilike(f"%{query_str}%"),
                            Location.city.ilike(f"%{query_str}%")
                        )
                    ).first()
                    if loc:
                        resolved_type = "location"
                        resolved_id = loc.id
                        
        # 2. Query network graph if resolved
        if resolved_type and resolved_id:
            graph_payload = get_network_for_entity(resolved_type, resolved_id)
            
            # Retrieve associated cases to feed to RAG context
            if resolved_type == "accused":
                acc = db.query(Accused).filter(Accused.id == resolved_id).first()
                if acc:
                    retrieved_cases = [serialize_case(c, include_narrative=True) for c in acc.cases]
            elif resolved_type == "location":
                loc = db.query(Location).filter(Location.id == resolved_id).first()
                if loc:
                    retrieved_cases = [serialize_case(c, include_narrative=True) for c in loc.cases]
                    
    finally:
        db.close()
        
    return {
        "retrieved_graph": graph_payload,
        "retrieved_cases": retrieved_cases,
        "entity": {**entity, "type": resolved_type, "id": resolved_id}
    }

def hybrid_search_node(state: AgentState) -> dict:
    """Node that combines structured and semantic search results."""
    # 1. Run structured search
    structured_cases = search_cases_structured(state["filters"])
    
    # 2. Run semantic search (passing state to reuse embedding logic)
    semantic_result = semantic_search_node(state)
    semantic_cases = semantic_result.get("retrieved_cases", [])
    
    # 3. Merge cases by FIR number to avoid duplicates
    merged_cases = {c["fir_number"]: c for c in structured_cases}
    for c in semantic_cases:
        if c["fir_number"] not in merged_cases:
            merged_cases[c["fir_number"]] = c
            
    return {"retrieved_cases": list(merged_cases.values())}

def synthesize_node(state: AgentState) -> dict:
    """Node that synthesizes retrieved data into final natural language response."""
    retrieved_cases = state["retrieved_cases"]
    message = state["message"]
    language = state["language"]
    session_id = state["session_id"]
    classification = state["classification"]
    is_trend = state["is_trend"]
    retrieved_graph = state["retrieved_graph"]
    
    # Call rag_service synthesis
    rag_res = synthesize_answer(message, retrieved_cases, language)
    answer = rag_res["answer"]
    citations = rag_res["citations"]
    
    # Save the last mentioned context to memory
    if session_id:
        if session_id not in SESSION_MEMORY:
            SESSION_MEMORY[session_id] = {}
            
        # Update last accused if graph search was performed
        if classification == "graph" and state["entity"].get("id"):
            SESSION_MEMORY[session_id]["last_accused_id"] = state["entity"]["id"]
            
        # Update last FIR if cases were retrieved
        if retrieved_cases:
            # Take the first case as the last mentioned FIR
            SESSION_MEMORY[session_id]["last_fir_number"] = retrieved_cases[0]["fir_number"]
            
            # If we didn't perform graph search, but the retrieved case has accused, store it too
            if not SESSION_MEMORY[session_id].get("last_accused_id") and retrieved_cases[0].get("accused"):
                SESSION_MEMORY[session_id]["last_accused_id"] = retrieved_cases[0]["accused"][0]["id"]

    # 4. Set visual details
    visual_type = "none"
    visual_payload = None
    
    if classification == "graph" and retrieved_graph and retrieved_graph.get("nodes"):
        visual_type = "network"
        visual_payload = retrieved_graph
    elif is_trend or "trend" in message.lower() or "count" in message.lower():
        visual_type = "trend"
        db = SessionLocal()
        try:
            msg_lower = message.lower()
            group_by = "district"
            if "month" in msg_lower or "monthly" in msg_lower:
                group_by = "month"
            elif "crime" in msg_lower or "type" in msg_lower:
                group_by = "crime_type"
            visual_payload = compute_trend_payload(state["filters"], db, group_by=group_by)
        finally:
            db.close()
            
    return {
        "answer": answer,
        "citations": citations,
        "visual_type": visual_type,
        "visual_payload": visual_payload
    }

# ----------------- Compile LangGraph -----------------

workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("classify", classify_node)
workflow.add_node("structured_search", structured_search_node)
workflow.add_node("semantic_search", semantic_search_node)
workflow.add_node("graph_search", graph_search_node)
workflow.add_node("hybrid_search", hybrid_search_node)
workflow.add_node("synthesize", synthesize_node)

# Set Entry Point
workflow.set_entry_point("classify")

# Define routing logic
def route_after_classify(state: AgentState) -> str:
    return state["classification"]

# Add Conditional Edges
workflow.add_conditional_edges(
    "classify",
    route_after_classify,
    {
        "structured": "structured_search",
        "semantic": "semantic_search",
        "graph": "graph_search",
        "hybrid": "hybrid_search"
    }
)

# Add Normal Edges
workflow.add_edge("structured_search", "synthesize")
workflow.add_edge("semantic_search", "synthesize")
workflow.add_edge("graph_search", "synthesize")
workflow.add_edge("hybrid_search", "synthesize")
workflow.add_edge("synthesize", END)

# Compile Router
chat_router = workflow.compile()

def process_chat_message(session_id: str, message: str, language: str = "en") -> dict:
    """Entry point to invoke the LangGraph agent for a message."""
    initial_state = {
        "message": message,
        "language": language,
        "session_id": session_id,
        "classification": "structured",
        "filters": {},
        "entity": {"type": None, "query": None, "id": None},
        "is_trend": False,
        "retrieved_cases": [],
        "retrieved_graph": None,
        "answer": "",
        "citations": [],
        "visual_type": "none",
        "visual_payload": None
    }
    
    # Run graph
    try:
        final_state = chat_router.invoke(initial_state)
        return {
            "session_id": session_id,
            "answer": final_state.get("answer", ""),
            "citations": final_state.get("citations", []),
            "visual_type": final_state.get("visual_type", "none"),
            "visual_payload": final_state.get("visual_payload", None)
        }
    except Exception as e:
        logger.error(f"LangGraph execution crashed: {e}")
        # Crash protection fallback
        return {
            "session_id": session_id,
            "answer": "An error occurred while processing your request. Please try again. (System Fallback)",
            "citations": [],
            "visual_type": "none",
            "visual_payload": None
        }
