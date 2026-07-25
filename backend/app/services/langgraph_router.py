import os
import json
import logging
import re
import numpy as np
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage

from sqlalchemy import or_
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
SESSION_MEMORY = {}  # session_id -> {"last_fir_number": str, "last_accused_id": int, "last_accused_name": str, "last_district": str}

def clear_session_memory(session_id: str):
    """Clear in-memory session context for a deleted session."""
    if session_id in SESSION_MEMORY:
        SESSION_MEMORY.pop(session_id, None)

class AgentState(TypedDict):
    message: str
    language: str
    session_id: str
    classification: str  # structured | semantic | graph | hybrid
    filters: Dict[str, Any]
    entity: Dict[str, Any]  # {"type": "accused"|"location"|None, "query": str|None, "id": int|None}
    is_trend: bool
    retrieved_cases: List[Dict[str, Any]]
    total_count: int
    returned_count: int
    offset: int
    limit: int
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
        name_str = f" ({mem.get('last_accused_name')})" if mem.get("last_accused_name") else ""
        context.append(f"Last mentioned Accused ID: {mem.get('last_accused_id')}{name_str}")
    if mem.get("last_district"):
        context.append(f"Last mentioned District: {mem.get('last_district')}")
    return "\n".join(context)

ACCUSED_PRONOUN_REGEX = re.compile(
    r'\b(his|her|their|them|he|she|him|this accused|the accused|that suspect|the suspect|that person)\b',
    re.IGNORECASE
)
LOCATION_PRONOUN_REGEX = re.compile(
    r'\b(there|that district|that city|that place|from there|in that area)\b',
    re.IGNORECASE
)

def resolve_session_pronouns(
    message: str, 
    filters: dict, 
    entity: dict, 
    classification: str, 
    session_id: Optional[str] = None
) -> tuple[dict, dict, str]:
    """
    Checks message for pronouns (accused or location) and resolves them against SESSION_MEMORY context.
    """
    msg_lower = message.lower()
    has_accused_pronoun = bool(ACCUSED_PRONOUN_REGEX.search(msg_lower))
    has_location_pronoun = bool(LOCATION_PRONOUN_REGEX.search(msg_lower))

    # 1. Accused Pronoun Resolution
    if has_accused_pronoun:
        query_str = entity.get("query")
        if query_str and ACCUSED_PRONOUN_REGEX.search(query_str.strip()):
            query_str = None
            entity["query"] = None

        if filters.get("accused_name") and ACCUSED_PRONOUN_REGEX.search(filters["accused_name"].strip()):
            filters["accused_name"] = None

        if not query_str and not entity.get("id"):
            if session_id and session_id in SESSION_MEMORY and SESSION_MEMORY[session_id].get("last_accused_id"):
                mem = SESSION_MEMORY[session_id]
                entity["type"] = "accused"
                entity["id"] = mem["last_accused_id"]
                entity["query"] = mem.get("last_accused_name") or f"Accused ID {mem['last_accused_id']}"
                classification = "graph"
                logger.info(
                    f"Resolved accused pronoun in session '{session_id}' to Accused ID {entity['id']} ({entity['query']})"
                )
            else:
                logger.warning(
                    f"Accused pronoun detected in '{message}', but no last_accused_id found in SESSION_MEMORY for session '{session_id}'"
                )

    # 2. Location Pronoun Resolution
    if has_location_pronoun and not filters.get("district"):
        if session_id and session_id in SESSION_MEMORY and SESSION_MEMORY[session_id].get("last_district"):
            mem = SESSION_MEMORY[session_id]
            filters["district"] = mem["last_district"]
            logger.info(
                f"Resolved location pronoun in session '{session_id}' to District '{filters['district']}'"
            )
        else:
            logger.warning(
                f"Location pronoun detected in '{message}', but no last_district found in SESSION_MEMORY for session '{session_id}'"
            )

    return filters, entity, classification

CRIME_TYPE_MAPPING = {
    "phishing": "Cybercrime",
    "cybercrime": "Cybercrime",
    "cyber": "Cybercrime",
    "electricity bill scam": "Cybercrime",
    "online fraud": "Cybercrime",
    "otp": "Cybercrime",
    "hack": "Cybercrime",
    "break-ins": "Burglary",
    "break-in": "Burglary",
    "housebreaking": "Burglary",
    "burglary": "Burglary",
    "armed robbery": "Robbery",
    "robbery": "Robbery",
    "snatching": "Robbery",
    "heist": "Robbery",
    "theft": "Theft",
    "stolen": "Theft",
    "shoplifting": "Theft",
    "murder": "Murder",
    "homicide": "Murder",
    "assault": "Assault",
    "extortion": "Extortion",
    "blackmail": "Extortion",
    "kidnapping": "Kidnapping",
    "abduction": "Kidnapping",
    "drug trafficking": "Drug Trafficking",
    "narcotics": "Drug Trafficking",
    "drug": "Drug Trafficking",
    "cheating": "Cheating",
    "fraud": "Cheating",
    "scam": "Cheating",
    "riot": "Riot"
}

CANONICAL_CRIME_TYPES = [
    "Robbery", "Theft", "Murder", "Assault", "Cybercrime",
    "Extortion", "Burglary", "Kidnapping", "Drug Trafficking", "Cheating", "Riot"
]

UNSUPPORTED_SCRIPT_REGEX = re.compile(
    r'[\u0C00-\u0C7F\u0900-\u097F\u0B80-\u0BFF\u0D00-\u0D7F\u0980-\u09FF\u0A80-\u0AFF]'
)  # Telugu, Devanagari (Hindi/Marathi), Tamil, Malayalam, Bengali, Gujarati

def is_unsupported_language(text: str) -> bool:
    if not text:
        return False
    return bool(UNSUPPORTED_SCRIPT_REGEX.search(text))

KANNADA_DISTRICT_MAP = {
    "ಮೈಸೂರು": "Mysuru", "ಮೈಸೂರಿನಲ್ಲಿ": "Mysuru", "ಮೈಸೂರಿನ": "Mysuru",
    "ಬೆಂಗಳೂರು": "Bengaluru", "ಬೆಂಗಳೂರಿನಲ್ಲಿ": "Bengaluru", "ಬೆಂಗಳೂರಿನ": "Bengaluru",
    "ಬೆಳಗಾವಿ": "Belagavi", "ಹುಬ್ಬಳ್ಳಿ": "Hubballi", "ಧಾರವಾಡ": "Dharwad",
    "ಮಂಗಳೂರು": "Mangaluru", "ಮಂಡ್ಯ": "Mandya", "ಕೋಲಾರ": "Kolar",
    "ಉಡುಪಿ": "Udupi", "ತುಮಕೂರು": "Tumakuru", "ಬೀದರ್": "Bidar",
    "ಕಲಬುರಗಿ": "Kalaburagi", "ಯಾದಗಿರಿ": "Yadgir", "ಚಾಮರಾಜನಗರ": "Chamarajanagar",
    "ಕೊಪ್ಪಳ": "Koppal", "ಹಾವೇರಿ": "Haveri", "ಗದಗ": "Gadag",
    "ಬಾಗಲಕೋಟೆ": "Bagalkot", "ವಿಜಯಪುರ": "Vijayapura", "ಚಿತ್ರದುರ್ಗ": "Chitradurga",
    "ದಾವಣಗೆರೆ": "Davanagere", "ಶಿವಮೊಗ್ಗ": "Shivamogga", "ರಾಮನಗರ": "Ramanagara",
    "ಚಿಕ್ಕಬಳ್ಳಾಪುರ": "Chikkaballapur", "ಬಳ್ಳಾರಿ": "Ballari"
}

KANNADA_CRIME_MAP = {
    "ಕಳ್ಳತನ": "Theft", "ಕಳ್ಳತನದ": "Theft", "ಕದ್ದ": "Theft",
    "ದರೋಡೆ": "Robbery", "ಕೊಲೆ": "Murder", "ದಾಳಿ": "Assault", "ಹಲ್ಲೆ": "Assault",
    "ಸೈಬರ್": "Cybercrime", "ಆನ್‌ಲೈನ್": "Cybercrime", "ಸುಲಿಗೆ": "Extortion",
    "ಕನ್ನಗಳವು": "Burglary", "ಅಪಹರಣ": "Kidnapping", "ವಂಚನೆ": "Cheating", "ಗಲಭೆ": "Riot"
}

def infer_and_normalize_crime_type(text: Optional[str]) -> Optional[str]:
    """Infers or normalizes raw crime string/text into canonical database crime_type."""
    if not text:
        return None
    text_lower = text.lower()

    # Check Kannada crime terms first
    for kn_term, canonical in KANNADA_CRIME_MAP.items():
        if kn_term in text:
            return canonical

    sorted_keys = sorted(CRIME_TYPE_MAPPING.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in text_lower:
            return CRIME_TYPE_MAPPING[key]
    for c in CANONICAL_CRIME_TYPES:
        if c.lower() in text_lower:
            return c
    return None

def heuristic_classify_and_extract(message: str, session_id: str = None) -> dict:
    """Perform rule-based classification and extraction as a fallback or pre-pass."""
    if is_unsupported_language(message):
        filters = {
            "crime_type": None,
            "district": None,
            "status": None,
            "date_from": None,
            "date_to": None,
            "accused_name": None,
            "is_unsupported_language": True
        }
        return {
            "classification": "structured",
            "filters": filters,
            "entity": {"type": None, "query": None, "id": None},
            "is_trend": False
        }

    msg_lower = message.lower()
    
    # 1. District heuristic (English + Kannada)
    found_district = None
    for kn_dist, en_dist in KANNADA_DISTRICT_MAP.items():
        if kn_dist in message:
            found_district = en_dist
            break

    if not found_district:
        districts = [
            "mysuru", "mysore", "bengaluru", "bangalore", "belagavi", "belgaum", 
            "hubballi", "hubli", "dharwad", "mangaluru", "mangalore", "mandya", 
            "kolar", "udupi", "tumakuru", "tumkur", "bidar", "kalaburagi", "gulbarga", 
            "yadgir", "chamarajanagar", "koppal", "haveri", "gadag", "bagalkot", 
            "vijayapura", "bijapur", "chitradurga", "davanagere", "shivamogga", "shimoga", 
            "ramanagara", "chikkaballapur", "ballari", "bellary", "chamarajanagara"
        ]
        for d in districts:
            if d in msg_lower:
                found_district = d.capitalize()
                if found_district in ["Mysore", "Mysuru"]:
                    found_district = "Mysuru"
                elif found_district in ["Bangalore", "Bengaluru"]:
                    found_district = "Bengaluru"
                break
            
    # 2. Crime type heuristic
    found_crime = infer_and_normalize_crime_type(message)

    # 3. Status heuristic
    statuses = ["closed", "open", "under investigation", "under_investigation", "pending", "chargesheeted", "registered"]
    found_status = None
    for s in statuses:
        if s in msg_lower:
            if s in ["under investigation", "under_investigation"]:
                found_status = "under_investigation"
            else:
                found_status = s
            break

    # 4. Dates heuristic
    date_matches = re.findall(r'\d{4}-\d{2}-\d{2}', message)
    date_from = date_matches[0] if len(date_matches) > 0 else None
    date_to = date_matches[1] if len(date_matches) > 1 else None
    
    year_match = re.search(r'\b(20\d{2})\b', message)
    if year_match and not date_from:
        year = year_match.group(1)
        date_from = f"{year}-01-01"
        date_to = f"{year}-12-31"

    # 5. Graph keywords heuristic
    graph_keywords = ["network", "connected", "connection", "link", "associate", "accomplice", "contacts", "relation", "relate", "friends", "graph", "cases of", "cases connected to"]
    is_graph = any(kw in msg_lower for kw in graph_keywords)
    
    # 6. Semantic keywords heuristic
    semantic_keywords = ["similar", "mo of", "mo involving", "mo with", "modus operandi", "describe", "narration", "pattern", "narrative", "deception", "daytime", "nighttime", "weapon"]
    is_semantic = any(kw in msg_lower for kw in semantic_keywords)
    
    # 7. Trend / Aggregation keywords heuristic
    trend_keywords = [
        "trend", "count", "number of", "how many", "statistics", "stats", "compare",
        "aggregation", "percentage", "percent", "distribution", "breakdown", "spread",
        "cases by", "by district", "by crime", "by type", "by status", "by month",
        "ratio", "proportion", "chart", "graph"
    ]
    trend_pattern = r'\b(?:trend|trends|count|counts|number of|how many|statistics|stats|aggregation|percentage|percentages|percent|distribution|distributions|breakdown|breakdowns|spread|ratio|proportion|proportions|chart|graph)\b|\bby\s+(?:district|crime|type|status|month)\b|\bcases\s+by\b'
    is_trend = any(kw in msg_lower for kw in trend_keywords) or bool(re.search(trend_pattern, msg_lower, re.IGNORECASE))

    # 8. Accused name or numeric ID extraction
    accused_name = None
    accused_id = None

    accused_id_match = re.search(r'\b(?:accused\s+(?:id|#)?|accused_id\s*=?)\s*#?\s*(\d+)\b', message, re.IGNORECASE)
    if accused_id_match:
        accused_id = int(accused_id_match.group(1))
    else:
        accused_match = re.search(r'(?:accused|suspect|connected to|linked to|associated with|related to|network for|accomplices of|cases of|for)\s+([A-Za-z]+(?:\s+[A-Za-z]\.)?)', message, re.IGNORECASE)
        if accused_match:
            extracted = accused_match.group(1).strip()
            if not ACCUSED_PRONOUN_REGEX.search(extracted):
                accused_name = extracted
        else:
            # Check for known named entities in message
            for known_name in ["ravi kumar", "mohammed naik", "darshan s", "kiran k"]:
                if known_name in msg_lower:
                    accused_name = known_name.title()
                    break

    has_entity = bool(accused_name or accused_id)
    has_attribute_filter = bool(found_district or found_crime or found_status or date_from)

    if is_graph or (has_entity and (is_graph or "case" in msg_lower or "cases" in msg_lower)):
        classification = "graph"
    elif is_semantic:
        if has_attribute_filter:
            classification = "hybrid"
        else:
            classification = "semantic"
    else:
        classification = "structured"

    filters = {
        "crime_type": found_crime,
        "district": found_district,
        "status": found_status,
        "date_from": date_from,
        "date_to": date_to,
        "accused_name": accused_name
    }
    entity = {
        "type": "accused" if has_entity else None,
        "query": accused_name or (f"Accused ID {accused_id}" if accused_id else None),
        "id": accused_id
    }

    filters, entity, classification = resolve_session_pronouns(message, filters, entity, classification, session_id)

    return {
        "classification": classification,
        "filters": filters,
        "entity": entity,
        "is_trend": is_trend
    }

def llm_classify_and_extract(message: str, session_id: str = None) -> dict:
    """Use ChatGPT to classify the intent and extract structured filters/entities."""
    if is_unsupported_language(message):
        filters = {
            "crime_type": None,
            "district": None,
            "status": None,
            "date_from": None,
            "date_to": None,
            "accused_name": None,
            "is_unsupported_language": True
        }
        return {
            "classification": "structured",
            "filters": filters,
            "entity": {"type": None, "query": None, "id": None},
            "is_trend": False
        }

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        return heuristic_classify_and_extract(message, session_id)
        
    session_context = get_session_context(session_id)
    
    system_prompt = (
        "You are an AI router for Karnataka Crime GPT.\n"
        "Your task is to classify the user's message and extract query filters and entities.\n\n"
        "LANGUAGE SUPPORT & TRANSLATION:\n"
        "- The application supports English and Kannada (ಕನ್ನಡ).\n"
        "- If the user query is written in Kannada (or contains Kannada terms), translate all extracted entity names, district names, and crime types to canonical English values (e.g. 'ಮೈಸೂರು' -> district: 'Mysuru', 'ಕಳ್ಳತನ' -> crime_type: 'Theft', 'ದರೋಡೆ' -> crime_type: 'Robbery', 'ಕೊಲೆ' -> crime_type: 'Murder', 'ಬೆಂಗಳೂರು' -> district: 'Bengaluru').\n"
        "- If the user query is written in an unsupported script/language other than English or Kannada (e.g. Telugu, Hindi, Tamil, Malayalam, Bengali, Marathi, etc.), set filters.is_unsupported_language = true.\n"
        "- If the user query consists of random gibberish or unparseable text with no identifiable crime investigation intent or filters, set filters.unparseable_query = true.\n\n"
        "Classifications:\n"
        "- `graph`: if the user is asking about network, connections, accomplices, links between accused, location connections, or cases connected/linked/related to an entity.\n"
        "- `semantic`: if the user is looking for cases based on textual descriptions, MO patterns, narrative similarities, or 'similar to FIR X' with NO structured attribute filters (district, status, dates).\n"
        "- `structured`: if the user is filtering cases by specific database column fields (e.g. status='closed', district name, crime type, dates) with NO entity reference or free-text MO description.\n"
        "- `hybrid`: if the query combines structured column filters (e.g. district, crime_type) AND free-text MO pattern / narrative descriptions (e.g. 'with MO involving daytime deception').\n\n"
        "CRITICAL ROUTING RULES:\n"
        "1. If a query combines structured column filters (e.g. district, crime_type) AND free-text MO pattern keywords (e.g. 'with MO involving...', 'narrative like...'), classify as `hybrid` and extract BOTH the structured filters AND the MO free-text.\n"
        "2. If a query mentions or asks about cases connected to / linked to / associated with a specific entity (accused or location), classify as `graph` and extract BOTH the entity (in entity.query) AND any structured filters (crime_type, district, status, dates, etc. in filters).\n"
        "3. Queries like 'Show me cases with status closed', 'Show me cases in Mysuru district', 'Show me all Robbery cases', or date filters with NO entity reference and NO free-text MO description MUST be classified as `structured`.\n"
        "4. Do NOT carry over filters (district, status, crime type) from previous session turns unless the user explicitly refers to them using pronouns (e.g., 'in that district', 'his cases').\n"
        "5. If the query describes a specific crime or MO (e.g. 'phishing', 'electricity bill scam' -> 'Cybercrime', 'break-ins' -> 'Burglary', 'armed robbery' -> 'Robbery'), infer and populate crime_type with a canonical crime type.\n\n"
        "You must output a JSON object with these EXACT keys:\n"
        "{\n"
        "  \"classification\": \"structured\" | \"semantic\" | \"graph\" | \"hybrid\",\n"
        "  \"filters\": {\n"
        "    \"crime_type\": \"Robbery\" | \"Theft\" | \"Murder\" | \"Assault\" | \"Cybercrime\" | \"Extortion\" | \"Burglary\" | \"Kidnapping\" | \"Drug Trafficking\" | \"Cheating\" | null,\n"
        "    \"district\": \"string or null\",\n"
        "    \"status\": \"string or null\" (e.g., \"closed\", \"open\", \"under_investigation\", \"pending\"),\n"
        "    \"date_from\": \"YYYY-MM-DD or null\",\n"
        "    \"date_to\": \"YYYY-MM-DD or null\",\n"
        "    \"accused_name\": \"string or null\",\n"
        "    \"is_unsupported_language\": true | false,\n"
        "    \"unparseable_query\": true | false\n"
        "  },\n"
        "  \"entity\": {\n"
        "    \"type\": \"accused\" | \"location\" | null,\n"
        "    \"query\": \"string or null\" (name of the accused or location details to search/graph)\n"
        "  },\n"
        "  \"is_trend\": true | false (true if the user is asking for trends, statistics, counts, distributions, breakdowns, percentages, proportions, comparisons, charts, or cases grouped by category e.g. 'show crime type distribution', 'breakdown of cases by district', 'crime type stats', 'percentage of each crime type', 'cases by crime type', 'how are cases distributed')\n"
        "}\n\n"
        f"Session Memory Context:\n{session_context or 'None'}\n"
        "Use the Session Memory Context ONLY to resolve pronouns (e.g. 'his cases' refers to the last mentioned Accused ID or name)."
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
        entity = parsed.get("entity", {})
        filters = parsed.get("filters", {})
        classification = parsed.get("classification", "structured")

        # If text does not contain unsupported script but LLM marked is_unsupported_language on Latin text, flip it to unparseable_query
        if not is_unsupported_language(message) and filters.get("is_unsupported_language"):
            filters["is_unsupported_language"] = False
            filters["unparseable_query"] = True

        # Check for explicit numeric Accused ID pattern override
        accused_id_match = re.search(r'\b(?:accused\s+(?:id|#)?|accused_id\s*=?)\s*#?\s*(\d+)\b', message, re.IGNORECASE)
        if accused_id_match:
            acc_id = int(accused_id_match.group(1))
            entity = {
                "type": "accused",
                "id": acc_id,
                "query": f"Accused ID {acc_id}"
            }
            classification = "graph"

        # Normalize crime_type
        if filters:
            raw_ct = filters.get("crime_type")
            norm_ct = infer_and_normalize_crime_type(raw_ct) or infer_and_normalize_crime_type(message)
            filters["crime_type"] = norm_ct

        # Resolve session pronouns
        filters, entity, classification = resolve_session_pronouns(message, filters, entity, classification, session_id)

        parsed["filters"] = filters
        parsed["entity"] = entity
        parsed["classification"] = classification

        if "is_trend" not in parsed or parsed.get("is_trend") is None:
            heur_res = heuristic_classify_and_extract(message, session_id)
            parsed["is_trend"] = heur_res["is_trend"]

        return parsed
    except Exception as e:
        logger.error(f"OpenAI Router API failed: {e}. Falling back to heuristics.")
        return heuristic_classify_and_extract(message, session_id)

# ----------------- Database / pgvector Helpers -----------------

SEMANTIC_CANDIDATE_LIMIT = 20
SEMANTIC_STRONG_DISTANCE_THRESHOLD = 0.15
SEMANTIC_LOOSE_DISTANCE_THRESHOLD = 0.22
SEMANTIC_WEAK_DISTANCE_THRESHOLD = SEMANTIC_LOOSE_DISTANCE_THRESHOLD
SEMANTIC_MAX_RELATED_COUNT = 5

def perform_vector_search(db, query_embedding: list, candidate_limit: int = SEMANTIC_CANDIDATE_LIMIT) -> list:
    """
    Performs pgvector cosine similarity search or SQLite fallback numpy cosine similarity.
    Returns a list of tuples: [(case_id: int, distance: float), ...]
    """
    if DATABASE_URL.startswith("postgresql"):
        try:
            results = db.query(
                CaseEmbedding.case_id,
                CaseEmbedding.embedding.cosine_distance(query_embedding).label("distance")
            ).order_by(
                CaseEmbedding.embedding.cosine_distance(query_embedding)
            ).limit(candidate_limit).all()
            return [(r[0], float(r[1])) for r in results]
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
            dist = 1.0 - sim
            
            matches.append((emb.case_id, dist))
            
        matches.sort(key=lambda x: x[1])
        return matches[:candidate_limit]

def compute_trend_payload(filters: dict, db, group_by: str = "district") -> dict:
    """Helper to query cases and return data grouped by district, crime_type, status, or month matching trend shape."""
    from sqlalchemy import func
    try:
        # Base query depends on group_by
        if group_by == "district":
            query = db.query(District.name, func.count(FIRCase.id)).join(FIRCase, FIRCase.district_id == District.id)
            group_field = District.name
        elif group_by == "crime_type":
            query = db.query(FIRCase.crime_type, func.count(FIRCase.id))
            group_field = FIRCase.crime_type
        elif group_by == "status":
            query = db.query(FIRCase.status, func.count(FIRCase.id))
            group_field = FIRCase.status
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
        if filters.get("district") and group_by != "district":
            query = query.join(District, FIRCase.district_id == District.id).filter(District.name.ilike(f"%{filters['district']}%"))

        if filters.get("crime_type") and group_by != "crime_type":
            query = query.filter(FIRCase.crime_type.ilike(f"%{filters['crime_type']}%"))

        if filters.get("status") and group_by != "status":
            query = query.filter(FIRCase.status.ilike(f"%{filters['status']}%"))
            
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
    cls = result.get("classification", "structured")
    if cls not in ["structured", "semantic", "graph", "hybrid"]:
        cls = "structured"
    return {
        "classification": cls,
        "filters": result.get("filters", {}),
        "entity": result.get("entity", {}),
        "is_trend": result.get("is_trend", False)
    }

def structured_search_node(state: AgentState) -> dict:
    """Node that performs structured case search."""
    filters = dict(state.get("filters", {}))
    msg = state.get("message", "")

    # 1. Unsupported language check
    if filters.get("is_unsupported_language") or is_unsupported_language(msg):
        filters["is_unsupported_language"] = True
        return {
            "retrieved_cases": [],
            "total_count": 0,
            "returned_count": 0,
            "filters": filters,
            "is_trend": False
        }

    # 2. Check if any actual attribute filter or explicit browse intent exists
    has_any_filter = bool(
        filters.get("district") or filters.get("crime_type") or filters.get("status") or
        filters.get("police_station") or filters.get("ipc_section") or filters.get("date_from") or
        filters.get("date_to") or filters.get("accused_name") or state.get("is_trend")
    )

    explicit_browse_terms = ["all cases", "browse cases", "list cases", "show cases", "show all", "list all"]
    is_explicit_browse = any(term in msg.lower() for term in explicit_browse_terms)

    # If classification produced NO filters and user did not explicitly ask to browse all cases, fail honestly!
    if not has_any_filter and not is_explicit_browse:
        logger.info(f"Query '{msg}' produced no usable filters and is not an explicit browse request.")
        return {
            "retrieved_cases": [],
            "total_count": 0,
            "returned_count": 0,
            "filters": {**filters, "unparseable_query": True},
            "is_trend": False
        }

    filters["offset"] = state.get("offset", 0)
    filters["limit"] = state.get("limit", 15)
    res = search_cases_structured(filters)
    return {
        "retrieved_cases": res.get("cases", []),
        "total_count": res.get("total_count", 0),
        "returned_count": res.get("returned_count", 0),
        "is_trend": state.get("is_trend", False)
    }

def perform_semantic_search_with_filters(message: str, filters: dict = None, session_id: str = None) -> dict:
    """
    Performs semantic vector search (or fallback text search) scoped STRICTLY to
    candidates matching any structured filters (district, crime_type, status, dates, etc.).
    Applies strong thresholding (dist <= SEMANTIC_STRONG_DISTANCE_THRESHOLD).
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    filters = filters or {}
    if filters.get("is_unsupported_language") or is_unsupported_language(message):
        filters["is_unsupported_language"] = True
        return {
            "retrieved_cases": [],
            "total_count": 0,
            "returned_count": 0,
            "filters": filters
        }

    if filters.get("unparseable_query"):
        return {
            "retrieved_cases": [],
            "total_count": 0,
            "returned_count": 0,
            "filters": filters
        }

    inferred_crime_type = filters.get("crime_type")
    if not inferred_crime_type:
        inferred_crime_type = infer_and_normalize_crime_type(message)

    db = SessionLocal()
    try:
        # 1. Check for explicit FIR number lookup FIRST
        fir_match = re.search(r'\b(?:FIR\s*|case\s+)?(KA-\d{4}-\d{3,4}|[A-Z]{2}-\d{4}-\d{3,4})\b', message, re.IGNORECASE)
        if not fir_match:
            fir_match = re.search(r'\bFIR\s+([A-Za-z0-9\-]{5,})\b', message, re.IGNORECASE)

        if fir_match:
            fir_num = fir_match.group(1).upper()
            source_case = db.query(FIRCase).filter(FIRCase.fir_number.ilike(f"%{fir_num}%")).first()
            if source_case:
                c_dict = serialize_case(source_case, include_narrative=True)
                c_dict["is_strong_match"] = True
                c_dict["is_weak_match"] = False
                return {
                    "retrieved_cases": [c_dict],
                    "total_count": 1,
                    "returned_count": 1,
                    "filters": filters
                }
            else:
                # FIR was specifically queried but NOT found in DB.
                # Do NOT fall back to arbitrary vector search or session memory category bleed.
                logger.info(f"FIR '{fir_num}' was specifically queried but not found in DB.")
                return {
                    "retrieved_cases": [],
                    "total_count": 0,
                    "returned_count": 0,
                    "filters": {**filters, "fir_not_found": fir_num}
                }

        # 2. Obtain candidate cases matching structured SQL filters FIRST
        query = db.query(FIRCase)
        has_structured_filters = False
        
        if filters.get("district"):
            has_structured_filters = True
            query = query.join(District, FIRCase.district_id == District.id).filter(
                District.name.ilike(f"%{filters['district']}%")
            )
        if filters.get("police_station"):
            has_structured_filters = True
            query = query.join(PoliceStation, FIRCase.police_station_id == PoliceStation.id).filter(
                PoliceStation.name.ilike(f"%{filters['police_station']}%")
            )
        if filters.get("crime_type"):
            has_structured_filters = True
            query = query.filter(FIRCase.crime_type.ilike(f"%{filters['crime_type']}%"))
        if filters.get("status"):
            has_structured_filters = True
            query = query.filter(FIRCase.status.ilike(f"%{filters['status']}%"))
        if filters.get("ipc_section"):
            has_structured_filters = True
            query = query.filter(FIRCase.ipc_sections.ilike(f"%{filters['ipc_section']}%"))
        if filters.get("date_from"):
            has_structured_filters = True
            query = query.filter(FIRCase.date_reported >= filters["date_from"])
        if filters.get("date_to"):
            has_structured_filters = True
            query = query.filter(FIRCase.date_reported <= filters["date_to"])

        if has_structured_filters:
            candidate_objs = query.all()
        else:
            candidate_objs = db.query(FIRCase).all()

        candidate_ids = {c.id for c in candidate_objs}
        candidate_by_id = {c.id: c for c in candidate_objs}

        strong_cases = []
        related_candidates = []
        query_text = message

        # 3. Vector search / semantic ranking scoped strictly to candidate_ids
        if openai_api_key:
            try:
                embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
                vector = embeddings.embed_query(query_text)
                search_results = perform_vector_search(db, vector, candidate_limit=SEMANTIC_CANDIDATE_LIMIT)
                
                # Filter vector search results to candidate_ids if structured filters were applied
                if has_structured_filters:
                    search_results = [res for res in search_results if res[0] in candidate_ids]

                for cid, dist in search_results:
                    case = candidate_by_id.get(cid) or db.query(FIRCase).filter(FIRCase.id == cid).first()
                    if case:
                        c_dict = serialize_case(case, include_narrative=True)
                        c_dict["distance"] = round(dist, 4)
                        c_dict["similarity_score"] = round(1.0 - dist, 4)
                        c_dict["is_strong_match"] = dist <= SEMANTIC_STRONG_DISTANCE_THRESHOLD
                        
                        if c_dict["is_strong_match"]:
                            c_dict["is_weak_match"] = False
                            strong_cases.append(c_dict)
                        elif SEMANTIC_STRONG_DISTANCE_THRESHOLD < dist <= SEMANTIC_LOOSE_DISTANCE_THRESHOLD and not has_structured_filters:
                            c_dict["is_weak_match"] = True
                            case_ct = c_dict.get("crime_type") or ""
                            if inferred_crime_type:
                                if case_ct.strip().lower() == inferred_crime_type.strip().lower() or inferred_crime_type.strip().lower() in case_ct.strip().lower():
                                    related_candidates.append(c_dict)
                            else:
                                related_candidates.append(c_dict)
            except Exception as e:
                logger.error(f"Semantic search embedding failed: {e}")
                mo_terms = [word for word in re.findall(r'\b[a-zA-Z]{3,}\b', message) if word.lower() not in ["find", "show", "cases", "with", "mo", "involving", "case", "the", "and", "for", "district", "crime", "type"]]
                for c in candidate_objs:
                    text_content = f"{c.mo_description or ''} {c.narrative or ''}".lower()
                    matches = [t.lower() in text_content for t in mo_terms if len(t) > 3]
                    if matches and all(matches):
                        c_dict = serialize_case(c, include_narrative=True)
                        c_dict["is_strong_match"] = True
                        c_dict["is_weak_match"] = False
                        strong_cases.append(c_dict)
                    elif matches and any(matches) and not has_structured_filters:
                        c_dict = serialize_case(c, include_narrative=True)
                        c_dict["is_strong_match"] = False
                        c_dict["is_weak_match"] = True
                        related_candidates.append(c_dict)
        else:
            # Local / fallback text search mode scoped strictly to candidate_objs
            mo_terms = [word for word in re.findall(r'\b[a-zA-Z]{3,}\b', message) if word.lower() not in ["find", "show", "cases", "with", "mo", "involving", "case", "the", "and", "for", "district", "crime", "type", "bengaluru", "urban", "mysuru", "robbery", "trafficking", "drug"]]
            for c in candidate_objs:
                text_content = f"{c.mo_description or ''} {c.narrative or ''}".lower()
                matches = [t.lower() in text_content for t in mo_terms if len(t) > 3]
                if matches and all(matches):
                    c_dict = serialize_case(c, include_narrative=True)
                    c_dict["is_strong_match"] = True
                    c_dict["is_weak_match"] = False
                    strong_cases.append(c_dict)
                elif matches and any(matches) and not has_structured_filters:
                    c_dict = serialize_case(c, include_narrative=True)
                    c_dict["is_strong_match"] = False
                    c_dict["is_weak_match"] = True
                    related_candidates.append(c_dict)

        # In hybrid search mode with structured filters, enforce that strong_cases MUST match any specified MO keywords
        if has_structured_filters and strong_cases:
            mo_terms = [
                word for word in re.findall(r'\b[a-zA-Z]{3,}\b', message)
                if word.lower() not in [
                    "find", "show", "cases", "with", "mo", "involving", "case", "the", "and", "for",
                    "district", "crime", "type", "bengaluru", "urban", "mysuru", "belagavi",
                    "robbery", "trafficking", "drug", "burglary", "cybercrime"
                ]
            ]
            if mo_terms:
                filtered_strong = []
                for c_dict in strong_cases:
                    text_content = f"{c_dict.get('mo_description') or ''} {c_dict.get('narrative') or ''}".lower()
                    matches = [term.lower() in text_content for term in mo_terms if len(term) > 3]
                    if matches and all(matches):
                        filtered_strong.append(c_dict)
                strong_cases = filtered_strong

        current_filters = dict(filters) if filters else {}
        if inferred_crime_type and not current_filters.get("crime_type"):
            current_filters["crime_type"] = inferred_crime_type

        # Structured Filter Fallback Tier:
        # If user provided structured filters (e.g. crime_type="Robbery"), but free-text semantic search yielded 0 strong matches,
        # fall back to returning the candidate cases matching the structured filters.
        if not strong_cases and not related_candidates and has_structured_filters and candidate_objs:
            fallback_cases = [serialize_case(c, include_narrative=True) for c in candidate_objs[:SEMANTIC_CANDIDATE_LIMIT]]
            for c in fallback_cases:
                c["is_strong_match"] = False
                c["is_structured_fallback"] = True
            current_filters["semantic_miss_fallback"] = True
            current_filters["unmatched_query_text"] = message
            return {
                "retrieved_cases": fallback_cases,
                "total_count": len(candidate_objs),
                "returned_count": len(fallback_cases),
                "filters": current_filters
            }

        # Fallback for un-filtered queries if no strong/weak matches
        if not strong_cases and not related_candidates and not has_structured_filters and inferred_crime_type:
            rel_cases = db.query(FIRCase).filter(
                FIRCase.crime_type.ilike(f"%{inferred_crime_type}%")
            ).limit(SEMANTIC_MAX_RELATED_COUNT).all()
            for c in rel_cases:
                c_dict = serialize_case(c, include_narrative=True)
                c_dict["is_strong_match"] = False
                c_dict["is_weak_match"] = True
                related_candidates.append(c_dict)

    finally:
        db.close()

    related_candidates.sort(key=lambda x: x.get("distance", 1.0))
    related_cases = related_candidates[:SEMANTIC_MAX_RELATED_COUNT] if not has_structured_filters else []

    retrieved_cases = strong_cases + related_cases
    total_cnt = len(strong_cases) if strong_cases else len(retrieved_cases)

    return {
        "retrieved_cases": retrieved_cases,
        "total_count": total_cnt,
        "returned_count": len(retrieved_cases),
        "filters": current_filters
    }

def semantic_search_node(state: AgentState) -> dict:
    """Node that performs threshold-filtered semantic embedding search."""
    return perform_semantic_search_with_filters(state["message"], filters=state.get("filters"), session_id=state["session_id"])

def graph_search_node(state: AgentState) -> dict:
    """Node that performs network graph searches with optional structured filter intersection."""
    entity = state["entity"]
    filters = state.get("filters", {})
    db = SessionLocal()
    graph_payload = {"nodes": [], "edges": []}
    retrieved_cases = []
    
    try:
        resolved_type = entity.get("type")
        resolved_id = entity.get("id")
        query_str = entity.get("query")
        if not query_str and filters.get("accused_name"):
            query_str = filters["accused_name"]
            
        # 1. Resolve entity if not already resolved by ID
        if not resolved_id and query_str:
            num_match = re.search(r'\b(\d+)\b', query_str)
            if num_match and (resolved_type == "accused" or not resolved_type or "accused" in query_str.lower()):
                possible_id = int(num_match.group(1))
                acc = db.query(Accused).filter(Accused.id == possible_id).first()
                if acc:
                    resolved_type = "accused"
                    resolved_id = acc.id
                    query_str = acc.name
                else:
                    resolved_type = "accused"
                    resolved_id = possible_id

            if not resolved_id and (resolved_type == "accused" or not resolved_type):
                acc = db.query(Accused).filter(Accused.name.ilike(f"%{query_str}%")).first()
                if acc:
                    resolved_type = "accused"
                    resolved_id = acc.id
                    query_str = acc.name
            if not resolved_id and (resolved_type == "location" or not resolved_type):
                loc = db.query(Location).filter(
                    or_(
                        Location.address.ilike(f"%{query_str}%"),
                        Location.city.ilike(f"%{query_str}%")
                    )
                ).first()
                if loc:
                    resolved_type = "location"
                    resolved_id = loc.id

        if resolved_id and (resolved_type == "accused" or not resolved_type):
            acc = db.query(Accused).filter(Accused.id == resolved_id).first()
            if acc:
                resolved_type = "accused"
                query_str = acc.name
            else:
                logger.info(f"Accused ID {resolved_id} was explicitly searched but not found in DB.")
                return {
                    "retrieved_graph": {"nodes": [], "edges": []},
                    "retrieved_cases": [],
                    "total_count": 0,
                    "returned_count": 0,
                    "entity": {**entity, "type": "accused", "id": resolved_id},
                    "filters": {**filters, "accused_not_found": resolved_id},
                    "is_trend": state.get("is_trend", False)
                }

        logger.info(f"Graph search node executing: type={resolved_type}, id={resolved_id}, query={query_str}, filters={filters}")
                        
        # 2. Query matching cases with filter intersection
        if resolved_type and resolved_id:
            query = db.query(FIRCase)
            if resolved_type == "accused":
                query = query.join(FIRCase.accused).filter(Accused.id == resolved_id)
            elif resolved_type == "location":
                query = query.filter(FIRCase.location_id == resolved_id)

            # Apply structured filters intersection
            if filters.get("district"):
                query = query.join(District, FIRCase.district_id == District.id).filter(
                    District.name.ilike(f"%{filters['district']}%")
                )
            if filters.get("police_station"):
                query = query.join(PoliceStation, FIRCase.police_station_id == PoliceStation.id).filter(
                    PoliceStation.name.ilike(f"%{filters['police_station']}%")
                )
            if filters.get("crime_type"):
                query = query.filter(FIRCase.crime_type.ilike(f"%{filters['crime_type']}%"))
            if filters.get("status"):
                query = query.filter(FIRCase.status.ilike(f"%{filters['status']}%"))
            if filters.get("ipc_section"):
                query = query.filter(FIRCase.ipc_sections.ilike(f"%{filters['ipc_section']}%"))
            if filters.get("date_from"):
                query = query.filter(FIRCase.date_reported >= filters["date_from"])
            if filters.get("date_to"):
                query = query.filter(FIRCase.date_reported <= filters["date_to"])

            case_objs = query.order_by(FIRCase.date_reported.desc()).all()
            retrieved_cases = [serialize_case(c, include_narrative=True) for c in case_objs]

            has_extra_filters = bool(
                filters.get("district") or filters.get("crime_type") or filters.get("status") or
                filters.get("ipc_section") or filters.get("police_station") or filters.get("date_from")
            )

            # Build network graph scoped to matching cases if extra filters exist, or full graph if pure entity search
            if has_extra_filters:
                graph_payload = get_network_for_entity(resolved_type, resolved_id, cases=case_objs)
            else:
                graph_payload = get_network_for_entity(resolved_type, resolved_id, cases=None)
        elif query_str and (resolved_type == "location" or not resolved_type):
            # Location/landmark query string could not be resolved to a Location table row ID (e.g. "MG Road" landmark in narrative text)
            query = db.query(FIRCase)
            if filters.get("district"):
                query = query.join(District, FIRCase.district_id == District.id).filter(
                    District.name.ilike(f"%{filters['district']}%")
                )
            if filters.get("crime_type"):
                query = query.filter(FIRCase.crime_type.ilike(f"%{filters['crime_type']}%"))
            if filters.get("status"):
                query = query.filter(FIRCase.status.ilike(f"%{filters['status']}%"))

            # Check if narrative or mo_description contains query_str (e.g. "MG Road")
            narrative_matches = query.filter(
                or_(
                    FIRCase.narrative.ilike(f"%{query_str}%"),
                    FIRCase.mo_description.ilike(f"%{query_str}%")
                )
            ).order_by(FIRCase.date_reported.desc()).all()

            if narrative_matches:
                retrieved_cases = [serialize_case(c, include_narrative=True) for c in narrative_matches]
                for c in retrieved_cases:
                    c["is_strong_match"] = True
            elif filters.get("crime_type"):
                # Structured Filter Fallback: fall back to all cases matching the structured crime_type filter
                all_crime_cases = query.order_by(FIRCase.date_reported.desc()).limit(15).all()
                retrieved_cases = [serialize_case(c, include_narrative=True) for c in all_crime_cases]
                for c in retrieved_cases:
                    c["is_strong_match"] = False
                    c["is_structured_fallback"] = True
                filters["semantic_miss_fallback"] = True
                filters["unmatched_query_text"] = state["message"]
                    
    finally:
        db.close()
        
    return {
        "retrieved_graph": graph_payload,
        "retrieved_cases": retrieved_cases,
        "total_count": len(retrieved_cases),
        "returned_count": len(retrieved_cases),
        "entity": {**entity, "type": resolved_type, "id": resolved_id},
        "is_trend": state.get("is_trend", False)
    }

def semantic_search_node(state: AgentState) -> dict:
    """Node that performs threshold-filtered semantic embedding search."""
    res = perform_semantic_search_with_filters(state["message"], filters=state.get("filters"), session_id=state["session_id"])
    res["is_trend"] = state.get("is_trend", False)
    return res

def hybrid_search_node(state: AgentState) -> dict:
    """Node that combines structured attribute filtering with semantic MO similarity search."""
    res = perform_semantic_search_with_filters(state["message"], filters=state.get("filters"), session_id=state["session_id"])
    res["is_trend"] = state.get("is_trend", False)
    return res

def synthesize_node(state: AgentState) -> dict:
    """Node that synthesizes retrieved data into final natural language response."""
    retrieved_cases = state["retrieved_cases"]
    total_count = state.get("total_count", len(retrieved_cases))
    returned_count = state.get("returned_count", len(retrieved_cases))
    offset = state.get("offset", 0)
    message = state["message"]
    language = state["language"]
    session_id = state["session_id"]
    classification = state["classification"]
    is_trend = state.get("is_trend", False)
    retrieved_graph = state.get("retrieved_graph")
    
    # Call rag_service synthesis
    rag_res = synthesize_answer(
        message, 
        retrieved_cases, 
        total_count=total_count, 
        returned_count=returned_count, 
        offset=offset,
        language=language,
        filters=state.get("filters")
    )
    answer = rag_res["answer"]
    citations = rag_res["citations"]
    
    # Save the last mentioned context to memory
    if session_id:
        if session_id not in SESSION_MEMORY:
            SESSION_MEMORY[session_id] = {}
            
        # Update last accused if graph search was performed
        if classification == "graph" and state.get("entity", {}).get("id"):
            SESSION_MEMORY[session_id]["last_accused_id"] = state["entity"]["id"]
            if state.get("entity", {}).get("query"):
                SESSION_MEMORY[session_id]["last_accused_name"] = state["entity"]["query"]
            
        # Update last FIR if cases were retrieved
        if retrieved_cases:
            # Take the first case as the last mentioned FIR
            SESSION_MEMORY[session_id]["last_fir_number"] = retrieved_cases[0]["fir_number"]
            
            # If we didn't perform graph search, but the retrieved case has accused, store it too
            if not SESSION_MEMORY[session_id].get("last_accused_id") and retrieved_cases[0].get("accused"):
                SESSION_MEMORY[session_id]["last_accused_id"] = retrieved_cases[0]["accused"][0]["id"]
                SESSION_MEMORY[session_id]["last_accused_name"] = retrieved_cases[0]["accused"][0].get("name")

            # Store last district if present in retrieved cases
            if retrieved_cases[0].get("district"):
                SESSION_MEMORY[session_id]["last_district"] = retrieved_cases[0]["district"]

        # Store last district if set in filters
        if state.get("filters", {}).get("district"):
            SESSION_MEMORY[session_id]["last_district"] = state["filters"]["district"]

    # 4. Set visual details
    visual_type = "none"
    visual_payload = None
    
    aggregation_terms = [
        "trend", "count", "distribution", "breakdown", "stats", "statistics", "percentage",
        "percent", "how many", "number of", "cases by", "by district", "by crime", "by type",
        "by status", "by month", "spread", "ratio", "proportion", "chart", "graph"
    ]
    is_agg_query = is_trend or any(kw in message.lower() for kw in aggregation_terms)

    if (classification == "graph" or (retrieved_graph and retrieved_graph.get("nodes"))) and retrieved_graph and retrieved_graph.get("nodes"):
        visual_type = "network"
        visual_payload = retrieved_graph
    elif is_agg_query or (total_count == 0 and any(kw in message.lower() for kw in aggregation_terms)):
        visual_type = "trend"
        db = SessionLocal()
        try:
            msg_lower = message.lower()
            if "status" in msg_lower:
                group_by = "status"
            elif "by district" in msg_lower or ("district" in msg_lower and "by crime" not in msg_lower and "crime type" not in msg_lower and "type" not in msg_lower):
                group_by = "district"
            elif "month" in msg_lower or "monthly" in msg_lower:
                group_by = "month"
            elif "crime" in msg_lower or "type" in msg_lower:
                group_by = "crime_type"
            else:
                group_by = "district"
            visual_payload = compute_trend_payload(state.get("filters", {}), db, group_by=group_by)
        finally:
            db.close()

        # For trend visual_type, clear citations, FIR case counts, and supply clean introductory narration for the chart
        citations = []
        total_count = 0
        returned_count = 0

        if language == "kn":
            if group_by == "status":
                answer = "ಕರ್ನಾಟಕದ ಜಿಲ್ಲೆಗಳಾದ್ಯಂತ ಪ್ರಕರಣಗಳ ಸ್ಥಿತಿಯ ವಿವರ ಇಲ್ಲಿದೆ:"
            elif group_by == "district":
                answer = "ಕರ್ನಾಟಕದ ಜಿಲ್ಲೆಗಳಾದ್ಯಂತ ಅಪರಾಧ ಪ್ರಕರಣಗಳ ಹಂಚಿಕೆ ವಿವರ ಇಲ್ಲಿದೆ:"
            elif group_by == "crime_type":
                answer = "ಕರ್ನಾಟಕದ ಎಲ್ಲಾ ನೋಂದಾಯಿತ ಪ್ರಕರಣಗಳಲ್ಲಿ ಅಪರಾಧ ಮಾದರಿಯ ಹಂಚಿಕೆ ವಿವರ ಇಲ್ಲಿದೆ:"
            elif group_by == "month":
                answer = "ವ್ಯವಸ್ಥೆಯಾದ್ಯಂತ ಅಪರಾಧ ಪ್ರಕರಣಗಳ ಮಾಸಿಕ ಪ್ರವೃತ್ತಿ ಇಲ್ಲಿದೆ:"
            else:
                answer = "ವ್ಯವಸ್ಥೆಯ ಡೇಟಾದ ಆಧಾರದ ಮೇಲೆ ಒಟ್ಟು ಅಪರಾಧ ಸಂಗ್ರಹಣೆ ಮತ್ತು ಪ್ರವೃತ್ತಿಯ ವಿವರ ಇಲ್ಲಿದೆ:"
        else:
            if group_by == "status":
                answer = "Here is the status breakdown of criminal cases across Karnataka:"
            elif group_by == "district":
                answer = "Here is the distribution of criminal cases by district across Karnataka:"
            elif group_by == "crime_type":
                answer = "Here is the crime type distribution breakdown across all registered cases in Karnataka:"
            elif group_by == "month":
                answer = "Here is the monthly trend of criminal cases across the system:"
            else:
                answer = "Here is the overall crime aggregation and trend breakdown based on system data:"
            
    return {
        "answer": answer,
        "citations": citations,
        "visual_type": visual_type,
        "visual_payload": visual_payload,
        "total_count": total_count,
        "returned_count": returned_count
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
    cls = state.get("classification", "structured")
    if cls not in ["structured", "semantic", "graph", "hybrid"]:
        return "structured"
    return cls

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

def process_chat_message(session_id: str, message: str, language: str = "en", offset: int = 0, limit: int = 15) -> dict:
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
        "total_count": 0,
        "returned_count": 0,
        "offset": offset,
        "limit": limit,
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
            "visual_payload": final_state.get("visual_payload", None),
            "total_count": final_state.get("total_count", 0),
            "returned_count": final_state.get("returned_count", 0),
            "offset": final_state.get("offset", offset),
            "limit": final_state.get("limit", limit)
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"LangGraph execution crashed: {e}")
        # Crash protection fallback
        return {
            "session_id": session_id,
            "answer": "An error occurred while processing your request. Please try again. (System Fallback)",
            "citations": [],
            "visual_type": "none",
            "visual_payload": None,
            "total_count": 0,
            "returned_count": 0,
            "offset": offset,
            "limit": limit
        }
