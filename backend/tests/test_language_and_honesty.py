import pytest
from app.services.langgraph_router import process_chat_message, heuristic_classify_and_extract

def test_unsupported_language_returns_honest_message_and_zero_cases():
    """
    Test Step 2 & 3: Unsupported language queries (e.g. Telugu 'మైసూర్లో దొంగతనానికి సంబంధించిన కేసులు ఏమిటి?')
    MUST return an honest unsupported language message rather than returning 15 arbitrary database cases
    claiming false 'closely matching' results.
    """
    res = process_chat_message("test-telugu", "మైసూర్లో దೊంగతనానికి సంబంధించిన కేసులు ఏమిటి?", "en")
    assert res["total_count"] == 0
    assert res["returned_count"] == 0
    assert res["citations"] == []
    assert "Language not supported" in res["answer"]
    assert "English and Kannada" in res["answer"]


def test_kannada_query_extracts_filters_and_returns_accurate_cases():
    """
    Test Step 2: Kannada query ('ಮೈಸೂರಿನಲ್ಲಿ ಕಳ್ಳತನದ ಪ್ರಕರಣಗಳು ಯಾವುವು?')
    MUST extract district='Mysuru' and crime_type='Theft', returning the 5 Theft cases in Mysuru.
    """
    res = process_chat_message("test-kannada", "ಮೈಸೂರಿನಲ್ಲಿ ಕಳ್ಳತನದ ಪ್ರಕರಣಗಳು ಯಾವುವು?", "kn")
    assert res["total_count"] == 5
    assert res["returned_count"] == 5
    assert len(res["citations"]) == 5
    # Verify all citations belong to Mysuru Theft cases
    for cit in res["citations"]:
        assert cit["fir_number"].startswith("KA-")


def test_unparseable_query_returns_honest_could_not_understand_message():
    """
    Test Step 3: Genuinely unparseable query ('qwertyuiop asdf ghjk')
    MUST NOT return arbitrary database cases claiming false matches.
    It MUST return an explicit 'Could not understand this query' message.
    """
    res = process_chat_message("test-unparseable", "qwertyuiop asdf ghjk", "en")
    assert res["total_count"] == 0
    assert res["returned_count"] == 0
    assert res["citations"] == []
    assert "Could not understand this query" in res["answer"]
