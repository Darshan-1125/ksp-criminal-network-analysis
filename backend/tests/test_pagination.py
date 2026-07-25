import os
import sys

# Ensure backend path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.langgraph_router import process_chat_message, SESSION_MEMORY
from app.services.db_service import search_cases_structured, format_case_record, format_status

def test_pagination_batch_size_sequence():
    """
    Test Step 1: For total_count=48 (Mysuru district) with page_size=15,
    retrieved batch sizes across successive offsets MUST be 15, 15, 15, 3.
    """
    session_id = "test-pagination-session"
    SESSION_MEMORY.clear()
    query = "Show me cases in Mysuru district"

    # Batch 1: offset 0
    res1 = process_chat_message(session_id, query, offset=0, limit=15)
    assert res1["total_count"] == 48
    assert res1["returned_count"] == 15
    assert res1["offset"] == 0
    assert "1. **FIR" in res1["answer"]
    assert "15. **FIR" in res1["answer"]

    # Batch 2: offset 15
    res2 = process_chat_message(session_id, query, offset=15, limit=15)
    assert res2["total_count"] == 48
    assert res2["returned_count"] == 15
    assert res2["offset"] == 15
    assert "16. **FIR" in res2["answer"]
    assert "30. **FIR" in res2["answer"]

    # Batch 3: offset 30
    res3 = process_chat_message(session_id, query, offset=30, limit=15)
    assert res3["total_count"] == 48
    assert res3["returned_count"] == 15
    assert res3["offset"] == 30
    assert "31. **FIR" in res3["answer"]
    assert "45. **FIR" in res3["answer"]

    # Batch 4: offset 45
    res4 = process_chat_message(session_id, query, offset=45, limit=15)
    assert res4["total_count"] == 48
    assert res4["returned_count"] == 3
    assert res4["offset"] == 45
    assert "46. **FIR" in res4["answer"]
    assert "48. **FIR" in res4["answer"]

    # Sequence assertion
    batch_sizes = [res1["returned_count"], res2["returned_count"], res3["returned_count"], res4["returned_count"]]
    assert batch_sizes == [15, 15, 15, 3]

def test_canonical_record_formatting_consistency():
    """
    Test Step 2: Ensure format_case_record outputs identical field set and Title Case status.
    """
    mock_case = {
        "fir_number": "KA-2024-9999",
        "crime_type": "Robbery",
        "ipc_sections": "IPC 392",
        "district": "Mysuru",
        "police_station": "Devaraja PS",
        "date_reported": "2024-05-12",
        "status": "under_investigation",
        "mo_description": "Suspects on bike snatched gold chain.",
        "accused": [{"id": 1, "name": "Ramesh"}],
        "victims": [{"id": 2, "name": "Suresh"}]
    }

    formatted = format_case_record(mock_case)
    assert "FIR KA-2024-9999" in formatted
    assert "**Crime Type**: Robbery" in formatted
    assert "**IPC**: IPC 392" in formatted
    assert "**District**: Mysuru" in formatted
    assert "**Police Station**: Devaraja PS" in formatted
    assert "**Date Reported**: 2024-05-12" in formatted
    assert "**Status**: Under Investigation" in formatted
    assert "**MO Description**: Suspects on bike snatched gold chain." in formatted
    assert "**Accused**: Ramesh" in formatted
    assert "**Victims**: Suresh" in formatted

def test_format_status_title_case():
    """
    Verify all raw database status values map to canonical Title Case display strings.
    """
    assert format_status("under_investigation") == "Under Investigation"
    assert format_status("closed") == "Closed"
    assert format_status("charge_sheeted") == "Charge Sheeted"
    assert format_status("chargesheeted") == "Charge Sheeted"
    assert format_status("pending") == "Pending"
    assert format_status("registered") == "Registered"

def test_new_query_resets_pagination_state():
    """
    Verify submitting a new distinct query resets total_count and offset cleanly.
    """
    session_id = "test-query-reset-session"
    SESSION_MEMORY.clear()

    # Query 1: Closed cases (total=180)
    q1 = "Show me cases with status closed"
    res1 = process_chat_message(session_id, q1, offset=0, limit=15)
    assert res1["total_count"] == 180
    assert res1["offset"] == 0
    assert res1["returned_count"] == 15

    # Query 2: Robbery cases (total=43)
    q2 = "Show me all Robbery cases"
    res2 = process_chat_message(session_id, q2, offset=0, limit=15)
    assert res2["total_count"] == 43
    assert res2["offset"] == 0
    assert res2["returned_count"] == 15

def test_no_exact_match_prints_no_exact_search_and_starts_from_1():
    """
    Verify that when no exact match exists (e.g. 'Find break-ins using metal cutters'),
    the output contains 'No exact search but related case' and numbering starts from 1.
    """
    from app.services.rag_service import synthesize_answer
    
    mock_weak_cases = [
        {
            "fir_number": "KA-2024-001",
            "crime_type": "Burglary",
            "ipc_sections": "IPC 457",
            "district": "Mysuru",
            "police_station": "Vijayanagar PS",
            "date_reported": "2024-03-01",
            "status": "under_investigation",
            "mo_description": "Break-in at shop",
            "accused": [],
            "victims": [],
            "is_strong_match": False
        },
        {
            "fir_number": "KA-2024-002",
            "crime_type": "Burglary",
            "ipc_sections": "IPC 457",
            "district": "Bengaluru",
            "police_station": "Indiranagar PS",
            "date_reported": "2024-03-05",
            "status": "pending",
            "mo_description": "House break-in",
            "accused": [],
            "victims": [],
            "is_strong_match": False
        }
    ]

    res = synthesize_answer("Find break-ins using metal cutters", mock_weak_cases)
    answer = res["answer"]
    
    # Must contain phrasing 'No exact search but related case'
    assert "No exact search but related case" in answer
    # Related cases list must start at 1. **FIR
    assert "1. **FIR KA-2024-001**" in answer
    assert "2. **FIR KA-2024-002**" in answer

def test_both_exact_and_related_cases_start_from_1():
    """
    Verify that when exact matches and related cases are both present,
    exact matches start from 1 and related cases section ALSO starts from 1.
    """
    from app.services.rag_service import synthesize_answer

    mock_retrieved = [
        # Strong match 1
        {
            "fir_number": "KA-2024-100",
            "crime_type": "Burglary",
            "ipc_sections": "IPC 457",
            "district": "Mysuru",
            "police_station": "Vijayanagar PS",
            "date_reported": "2024-03-01",
            "status": "under_investigation",
            "mo_description": "Break-in with cutter",
            "accused": [],
            "victims": [],
            "is_strong_match": True
        },
        # Weak match 1 (Related case)
        {
            "fir_number": "KA-2024-200",
            "crime_type": "Burglary",
            "ipc_sections": "IPC 457",
            "district": "Bengaluru",
            "police_station": "Indiranagar PS",
            "date_reported": "2024-03-05",
            "status": "pending",
            "mo_description": "House break-in",
            "accused": [],
            "victims": [],
            "is_strong_match": False
        }
    ]

    res = synthesize_answer("Find break-ins using cutter", mock_retrieved)
    answer = res["answer"]

    # Exact match section should have 1. **FIR KA-2024-100**
    assert "1. **FIR KA-2024-100**" in answer
    # Related cases section should ALSO start from 1. **FIR KA-2024-200** (not 2.)
    assert "1. **FIR KA-2024-200**" in answer

def test_filtered_entity_query_returns_intersected_cases_and_network_graph():
    """
    Regression Test (Bug 1 & Bug 2):
    Querying 'Show me robbery cases in Mysuru connected to Ravi Kumar'
    must return EXACTLY 1 case (KA-2024-1123) and visual_type='network' with scoped graph.
    """
    session_id = "test-entity-filter-intersection"
    SESSION_MEMORY.clear()
    
    query = "Show me robbery cases in Mysuru connected to Ravi Kumar"
    res = process_chat_message(session_id, query, offset=0, limit=15)

    assert res["total_count"] == 1
    assert res["returned_count"] == 1
    assert "KA-2024-1123" in res["answer"]
    assert res["visual_type"] == "network"
    assert res["visual_payload"] is not None
    assert "nodes" in res["visual_payload"]
    assert any("KA-2024-1123" in str(n.get("label")) for n in res["visual_payload"]["nodes"])

def test_pure_entity_lookup_returns_all_cases_unfiltered():
    """
    Verify pure entity lookup queries return their full unfiltered case sets.
    - 'Show me the network for Ravi Kumar' -> 6 cases
    - 'Who are Mohammed Naik\'s accomplices?' -> 16 cases
    """
    session_id = "test-pure-entity-lookup"
    SESSION_MEMORY.clear()

    res_ravi = process_chat_message(session_id, "Show me the network for Ravi Kumar", offset=0, limit=15)
    assert res_ravi["total_count"] == 6
    assert res_ravi["visual_type"] == "network"

    res_mohammed = process_chat_message(session_id, "Who are Mohammed Naik's accomplices?", offset=0, limit=15)
    assert res_mohammed["total_count"] == 16
    assert res_mohammed["visual_type"] == "network"

def test_plain_query_returns_no_network_graph():
    """
    Verify plain filter query with no entity reference returns visual_type='none'.
    """
    session_id = "test-plain-query-no-graph"
    SESSION_MEMORY.clear()

    res = process_chat_message(session_id, "Show me all robbery cases", offset=0, limit=15)
    assert res["total_count"] > 0
    assert res["visual_type"] == "none"

def test_hybrid_search_intersection_returns_exact_single_case():
    """
    Regression Test (Hybrid Search Fix):
    Querying 'Find Drug Trafficking cases in Bengaluru Urban with MO involving daytime deception'
    must return EXACTLY 1 case (KA-2024-1201) against the seeded database.
    """
    session_id = "test-hybrid-intersection"
    SESSION_MEMORY.clear()

    query = "Find Drug Trafficking cases in Bengaluru Urban with MO involving daytime deception"
    res = process_chat_message(session_id, query, offset=0, limit=15)

    assert res["total_count"] == 1
    assert res["returned_count"] == 1
    assert "KA-2024-1201" in res["answer"]

def test_trend_query_synonyms_render_trend_charts():
    """
    Regression Test (Trend Query Fix):
    Verify that all common trend/aggregation phrasings route to trend node and render charts:
    - 'show crime type distribution' -> crime_type pie chart
    - 'show crime trend by district' -> district bar chart
    - 'cases by crime type' -> crime_type pie chart
    - 'crime type breakdown' -> crime_type pie chart
    - 'what's the breakdown of cases by district' -> district bar chart
    """
    session_id = "test-trend-phrasings"
    SESSION_MEMORY.clear()

    # 1. show crime type distribution
    res_1 = process_chat_message(session_id, "show crime type distribution")
    assert res_1["visual_type"] == "trend"
    assert res_1["visual_payload"] is not None
    assert res_1["visual_payload"]["group_by"] == "crime_type"
    assert len(res_1["visual_payload"]["data"]) > 0

    # 2. show crime trend by district
    res_2 = process_chat_message(session_id, "show crime trend by district")
    assert res_2["visual_type"] == "trend"
    assert res_2["visual_payload"] is not None
    assert res_2["visual_payload"]["group_by"] == "district"
    assert len(res_2["visual_payload"]["data"]) > 0

    # 3. cases by crime type
    res_3 = process_chat_message(session_id, "cases by crime type")
    assert res_3["visual_type"] == "trend"
    assert res_3["visual_payload"] is not None
    assert res_3["visual_payload"]["group_by"] == "crime_type"

    # 4. crime type breakdown
    res_4 = process_chat_message(session_id, "crime type breakdown")
    assert res_4["visual_type"] == "trend"
    assert res_4["visual_payload"] is not None
    assert res_4["visual_payload"]["group_by"] == "crime_type"

    # 5. what's the breakdown of cases by district
    res_5 = process_chat_message(session_id, "what's the breakdown of cases by district")
    assert res_5["visual_type"] == "trend"
    assert res_5["visual_payload"] is not None
    assert res_5["visual_payload"]["group_by"] == "district"

def test_empty_search_result_fallback_message():
    """
    Regression Test (Empty Result Fallback):
    When a non-trend query returns 0 results, it must state what was searched for
    and suggest valid search alternatives rather than returning a bare dead-end message.
    """
    session_id = "test-empty-fallback"
    SESSION_MEMORY.clear()

def test_empty_search_result_fallback_message():
    """
    Regression Test (Empty Result Fallback):
    When a non-trend query returns 0 results, it must state what was searched for
    and suggest valid search alternatives rather than returning a bare dead-end message.
    """
    session_id = "test-empty-fallback"
    SESSION_MEMORY.clear()

    res = process_chat_message(session_id, "show me fraud cases in nonexistent_place_xyz")
    assert res["visual_type"] == "none"
    assert "No cases found matching" in res["answer"]
    assert "nonexistent_place_xyz" in res["answer"]
    assert "did you mean to see the crime type distribution" in res["answer"]

def test_case_status_breakdown_and_sequence():
    """
    Regression Test (Status Breakdown & Single Session Sequence):
    1. 'Show crime type distribution' -> crime_type pie chart
    2. 'Show case status breakdown' -> status breakdown (closed: 180, under_investigation: 164, charge_sheeted: 156), total_count=0 (no pagination), no text duplication
    3. 'Show crime cases by district' -> district bar chart
    """
    session_id = "test-status-seq-session"
    SESSION_MEMORY.clear()

    # Turn 1: Crime type distribution
    res_1 = process_chat_message(session_id, "Show crime type distribution")
    assert res_1["visual_type"] == "trend"
    assert res_1["visual_payload"]["group_by"] == "crime_type"

    # Turn 2: Case status breakdown
    res_2 = process_chat_message(session_id, "Show case status breakdown")
    assert res_2["visual_type"] == "trend"
    assert res_2["visual_payload"] is not None
    assert res_2["visual_payload"]["group_by"] == "status"
    assert res_2["total_count"] == 0
    assert res_2["returned_count"] == 0

    status_data = {item["key"]: item["count"] for item in res_2["visual_payload"]["data"]}
    assert status_data.get("closed") == 180
    assert status_data.get("under_investigation") == 164
    assert status_data.get("charge_sheeted") == 156

    # Verify no text duplication in answer
    ans_text = res_2["answer"]
    assert ans_text.count("Here is the status breakdown of criminal cases across Karnataka:") == 1

    # Turn 3: Crime cases by district
    res_3 = process_chat_message(session_id, "Show crime cases by district")
    assert res_3["visual_type"] == "trend"
    assert res_3["visual_payload"]["group_by"] == "district"
    assert "Here is the distribution of criminal cases by district across Karnataka:" in res_3["answer"]


def test_session_memory_accused_pronoun_resolution():
    """
    Regression Test: Session memory pronoun resolution for accused entities.
    Turn 1: "Show me Mohammed Naik's cases" -> Expect 16 cases.
    Turn 2: "What about his other Murder cases?" -> Expect exactly 2 cases (KA-2024-1234, KA-2024-1293).
    """
    session_id = "test-session-accused-pronoun"
    SESSION_MEMORY.clear()

    # Turn 1: Show me Mohammed Naik's cases
    res1 = process_chat_message(session_id, "Show me Mohammed Naik's cases")
    assert res1["total_count"] == 16
    assert SESSION_MEMORY.get(session_id, {}).get("last_accused_name") == "Mohammed Naik"

    # Turn 2: What about his other Murder cases?
    res2 = process_chat_message(session_id, "What about his other Murder cases?")
    assert res2["total_count"] == 2
    assert res2["returned_count"] == 2
    assert "KA-2024-1234" in res2["answer"]
    assert "KA-2024-1293" in res2["answer"]


def test_session_memory_location_pronoun_resolution():
    """
    Regression Test: Session memory pronoun resolution for location/district context.
    Turn 1: "Show me cases in Mysuru" -> Mysuru cases.
    Turn 2: "Show me the closed ones from there" -> Mysuru district cases with status='closed'.
    """
    session_id = "test-session-location-pronoun"
    SESSION_MEMORY.clear()

    # Turn 1: Show me cases in Mysuru
    res1 = process_chat_message(session_id, "Show me cases in Mysuru")
    assert res1["total_count"] == 48
    assert SESSION_MEMORY.get(session_id, {}).get("last_district") == "Mysuru"

    # Turn 2: Show me the closed ones from there
    res2 = process_chat_message(session_id, "Show me the closed ones from there")
    assert res2["total_count"] > 0
    assert res2["returned_count"] > 0


def test_nonexistent_fir_lookup_does_not_leak_stale_session_category():
    """
    Regression Test (Bug 1):
    Querying a nonexistent FIR number ("Summarize case KA-9999-9999") after discussing Cybercrime cases
    must state clearly that FIR KA-9999-9999 was not found, with 0 results and NO stale category leak.
    """
    session_id = "test-session-nonexistent-fir"
    SESSION_MEMORY.clear()

    # Turn 1: Discuss Cybercrime cases
    res1 = process_chat_message(session_id, "Show me Cybercrime cases")
    assert res1["total_count"] > 0

    # Turn 2: Summarize case KA-9999-9999
    res2 = process_chat_message(session_id, "Summarize case KA-9999-9999")
    assert res2["total_count"] == 0
    assert res2["returned_count"] == 0
    assert "KA-9999-9999" in res2["answer"]
    assert "was not found in the system" in res2["answer"]
    assert "other Cybercrime cases with a similar pattern" not in res2["answer"]


def test_semantic_miss_with_structured_crime_type_filter_falls_back_to_crime_type_cases():
    """
    Regression Test (Bug 2):
    1. Querying 'Tell me about the robbery near MG Road' matches the 2 Robbery cases containing 'MG Road' in narrative text.
    2. Querying 'Tell me about the robbery near NonexistentLandmarkXYZ' yields 0 free-text matches, falling back to all Robbery cases with honest caveat narration.
    """
    session_id = "test-session-semantic-miss-fallback"
    SESSION_MEMORY.clear()

    # Part 1: Narrative text match
    res1 = process_chat_message(session_id, "Tell me about the robbery near MG Road")
    assert res1["total_count"] > 0
    assert res1["returned_count"] > 0
    assert "Robbery" in res1["answer"] or "KA-2024-1123" in res1["answer"]

    # Part 2: Total semantic miss with structured crime_type filter -> Structured fallback tier
    res2 = process_chat_message(session_id, "Tell me about the robbery near NonexistentLandmarkXYZ")
    assert res2["total_count"] > 0
    assert res2["returned_count"] > 0
    assert "No cases specifically matched" in res2["answer"] or "showing all" in res2["answer"]
    assert "Robbery" in res2["answer"]


def test_numeric_accused_id_72_lookup_returns_mohammed_naik_cases():
    """
    Regression Test:
    Querying 'Show other cases for accused ID 72' must extract Accused ID 72 (Mohammed Naik),
    returning all 16 cases and a working network graph.
    """
    session_id = "test-session-accused-id-72"
    SESSION_MEMORY.clear()

    res = process_chat_message(session_id, "Show other cases for accused ID 72")
    assert res["total_count"] == 16
    assert res["returned_count"] > 0
    assert res["visual_type"] == "network"
    assert res["visual_payload"] is not None
    assert len(res["visual_payload"]["nodes"]) > 0


def test_numeric_accused_id_32_lookup_returns_faras_naidu_cases():
    """
    Regression Test:
    Querying 'Show other cases for accused ID 32' must extract Accused ID 32 (Faras Naidu),
    returning 6 cases.
    """
    session_id = "test-session-accused-id-32"
    SESSION_MEMORY.clear()

    res = process_chat_message(session_id, "Show other cases for accused ID 32")
    assert res["total_count"] == 6
    assert res["returned_count"] == 6


def test_nonexistent_accused_id_returns_explicit_not_found_message():
    """
    Regression Test:
    Querying a non-existent accused ID ('Show other cases for accused ID 99999')
    must return 'Accused with ID 99999 was not found in the system.' with 0 cases.
    """
    session_id = "test-session-accused-id-99999"
    SESSION_MEMORY.clear()

    res = process_chat_message(session_id, "Show other cases for accused ID 99999")
    assert res["total_count"] == 0
    assert res["returned_count"] == 0
    assert "Accused with ID 99999 was not found in the system" in res["answer"]








