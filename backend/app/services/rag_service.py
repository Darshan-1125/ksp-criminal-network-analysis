import os
import re
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.db_service import format_case_record

logger = logging.getLogger(__name__)

def synthesize_answer(
    message: str, 
    retrieved_cases: list, 
    total_count: int = 0, 
    returned_count: int = 0, 
    offset: int = 0,
    language: str = "en",
    filters: dict = None
) -> dict:
    """
    Synthesize retrieved records into a natural-language response.
    System prompt generates introductory narration, while Python backend constructs
    the canonical case record list using format_case_record().
    Returns:
      {
        "answer": str,
        "citations": [{"fir_number": str, "snippet": str}]
      }
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if total_count == 0 and len(retrieved_cases) > 0:
        total_count = len(retrieved_cases)
    if returned_count == 0:
        returned_count = len(retrieved_cases)

    if not retrieved_cases:
        if filters and filters.get("is_unsupported_language"):
            if language == "kn":
                no_cases_msg = "ಈ ಭಾಷೆಗೆ ಬೆಂಬಲವಿಲ್ಲ. ಕರ್ನಾಟಕ ಕ್ರೈಮ್ GPT ಪ್ರಸ್ತುತ ಇಂಗ್ಲಿಷ್ ಮತ್ತು ಕನ್ನಡ (ಕನ್ನಡ) ಭಾಷೆಗಳನ್ನು ಬೆಂಬಲಿಸುತ್ತದೆ. ದಯವಿಟ್ಟು ಇಂಗ್ಲಿಷ್ ಅಥವಾ ಕನ್ನಡದಲ್ಲಿ ಮರುರೂಪಿಸಿ."
            else:
                no_cases_msg = "Language not supported. Karnataka Crime GPT currently supports English and Kannada (ಕನ್ನಡ). Please rephrase your query in English or Kannada."
            return {"answer": no_cases_msg, "citations": []}

        if filters and filters.get("unparseable_query"):
            if language == "kn":
                no_cases_msg = "ಈ ಪ್ರಶ್ನೆಯನ್ನು ಅರ್ಥಮಾಡಿಕೊಳ್ಳಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ — ದಯವಿಟ್ಟು ನಿರ್ದಿಷ್ಟ ಅಪರಾಧ ಮಾದರಿ (ಉದಾ. ಕಳ್ಳತನ, ದರೋಡೆ), ಜಿಲ್ಲೆ (ಉದಾ. ಮೈಸೂರು, ಬೆಂಗಳೂರು), ಅಥವಾ ಎಫ್‌ಐಆರ್ ಸಂಖ್ಯೆಯೊಂದಿಗೆ ಮರುರೂಪಿಸಿ."
            else:
                no_cases_msg = "Could not understand this query — please try rephrasing with a specific crime type (e.g. Theft, Robbery), district (e.g. Mysuru, Bengaluru), or case/FIR number."
            return {"answer": no_cases_msg, "citations": []}

        if filters and filters.get("fir_not_found"):
            fir_num = filters["fir_not_found"]
            if language == "kn":
                no_cases_msg = f"FIR ಪ್ರಕರಣ '{fir_num}' ವ್ಯವಸ್ಥೆಯಲ್ಲಿ ಕಂಡುಬಂದಿಲ್ಲ."
            else:
                no_cases_msg = f"FIR case '{fir_num}' was not found in the system."
            return {"answer": no_cases_msg, "citations": []}

        if filters and filters.get("accused_not_found"):
            acc_id = filters["accused_not_found"]
            if language == "kn":
                no_cases_msg = f"ಆರೋಪಿ ID {acc_id} ವ್ಯವಸ್ಥೆಯಲ್ಲಿ ಕಂಡುಬಂದಿಲ್ಲ."
            else:
                no_cases_msg = f"Accused with ID {acc_id} was not found in the system."
            return {"answer": no_cases_msg, "citations": []}

        if language == "kn":
            no_cases_msg = f"ಯಾವುದೇ ಪ್ರಕರಣಗಳು ಸಿಗಲಿಲ್ಲ '{message}' — ಅಪರಾಧ ಮಾದರಿಯ ಹಂಚಿಕೆಯನ್ನು ನೋಡಲು ಬಯಸುವಿರಾ, ಅಥವಾ ನಿರ್ದಿಷ್ಟ ಜಿಲ್ಲೆ/ಅಪರಾಧವನ್ನು ಹುಡುಕುವಿರಾ?"
        else:
            no_cases_msg = f"No cases found matching '{message}' — did you mean to see the crime type distribution, or search a specific crime type or district?"
        return {"answer": no_cases_msg, "citations": []}

    # Handle structured fallback tier (when free-text semantic search missed, but structured filter succeeded)
    if filters and filters.get("semantic_miss_fallback"):
        raw_query = filters.get("unmatched_query_text") or message
        cleaned_text = re.sub(
            r'^(?:tell\s+me\s+about\s+the|tell\s+me\s+about|show\s+me\s+the|show\s+me|find\s+the|find)\s+',
            '', raw_query, flags=re.IGNORECASE
        ).strip()

        crime_type_val = filters.get("crime_type") or "matching"
        district_val = filters.get("district")
        district_str = f" in {district_val}" if district_val else ""

        if language == "kn":
            intro_narration = f"'{cleaned_text}' ಗಾಗಿ ನಿರ್ದಿಷ್ಟ ಪ್ರಕರಣಗಳು ಸಿಗಲಿಲ್ಲ — ಅದರ ಬದಲಾಗಿ ಎಲ್ಲಾ {total_count} {crime_type_val} ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಲಾಗುತ್ತಿದೆ{district_str}:"
        else:
            intro_narration = f"No cases specifically matched '{cleaned_text}' — showing all {total_count} {crime_type_val} cases instead{district_str}:"

        case_list_markdown = "\n\n".join([
            format_case_record(c, index=offset + idx + 1)
            for idx, c in enumerate(retrieved_cases)
        ])

        citations = []
        for c in retrieved_cases:
            fir = c.get("fir_number")
            if fir:
                snippet = c.get("mo_description") or (c.get("narrative") or "")[:200]
                citations.append({
                    "fir_number": fir,
                    "snippet": snippet
                })

        return {
            "answer": f"{intro_narration}\n\n{case_list_markdown}".strip(),
            "citations": citations
        }

    # 1. Partition cases into strong vs weak matches
    strong_cases = [c for c in retrieved_cases if c.get("is_strong_match", True)]
    weak_cases = [c for c in retrieved_cases if not c.get("is_strong_match", True)]

    strong_count = len(strong_cases)
    weak_count = len(weak_cases)

    # Determine crime type and district for honest framing & structured nudge
    crime_type_val = (filters.get("crime_type") if filters else None)
    if not crime_type_val and weak_cases:
        crime_type_val = weak_cases[0].get("crime_type")
    
    crime_type_str = crime_type_val if crime_type_val else "matching"
    district_val = (filters.get("district") if filters else None)
    district_str = f" in {district_val}" if district_val else ""

    nudge_msg = f"💡 *Want to see all {crime_type_str} cases{district_str}? Use structured search filters for full browsing and pagination.*"

    # 2. Build canonical markdown text
    if strong_count > 0:
        strong_markdown = "\n\n".join([
            format_case_record(c, index=offset + idx + 1)
            for idx, c in enumerate(strong_cases)
        ])
        if weak_count > 0:
            weak_markdown = "\n\n".join([
                format_case_record(c, index=offset + idx + 1)
                for idx, c in enumerate(weak_cases)
            ])
            case_list_markdown = (
                f"{strong_markdown}\n\n"
                f"### Related {crime_type_str} Cases\n"
                f"*{weak_count} other {crime_type_str} cases with a similar pattern:*\n\n"
                f"{weak_markdown}\n\n"
                f"{nudge_msg}"
            )
        else:
            case_list_markdown = strong_markdown
    else:
        if weak_count > 0:
            weak_markdown = "\n\n".join([
                format_case_record(c, index=offset + idx + 1)
                for idx, c in enumerate(weak_cases)
            ])
            case_list_markdown = (
                f"### Related {crime_type_str} Cases\n"
                f"*{weak_count} other {crime_type_str} cases with a similar pattern:*\n\n"
                f"{weak_markdown}\n\n"
                f"{nudge_msg}"
            )
        else:
            case_list_markdown = ""

    # 3. Derive citations deterministically for ALL retrieved cases in the batch
    citations = []
    for c in retrieved_cases:
        fir = c.get("fir_number")
        if fir:
            snippet = c.get("mo_description") or (c.get("narrative") or "")[:200]
            citations.append({
                "fir_number": fir,
                "snippet": snippet
            })

    # 4. Formulate LLM prompts for intro narration ONLY
    if total_count > 50:
        system_prompt = (
            "You are Karnataka Crime GPT, an assistant specializing in analyzing Karnataka crime records.\n"
            "The database search returned a large matching set.\n"
            "Your task is to provide an aggregated summary breakdown (counts by crime type or district if available) in 2-3 sentences.\n"
            "State the total count explicitly and inform the user they can narrow their query or request specific record batches.\n"
            "CRITICAL: Do NOT list individual FIR numbers or case bullets, as the backend will append the record list.\n"
            f"Total matching cases in DB: {total_count}. Shown in this batch: {returned_count}.\n"
            f"Answer in requested language: {language}.\n"
        )
    elif strong_count > 0:
        system_prompt = (
            "You are Karnataka Crime GPT, an assistant specializing in analyzing Karnataka crime records.\n"
            "Your task is to provide ONLY a brief 1-2 sentence introduction / header summarizing the query results.\n\n"
            "CRITICAL RULES:\n"
            "1. Do NOT list individual FIR case details, bullet points, or numbers in your response — the case record list will be automatically formatted and appended by the system.\n"
            f"2. State the count of closely matching cases clearly in your intro (e.g. 'Found {strong_count} cases closely matching your query criteria:').\n"
            f"3. Never state a count higher than {strong_count} for closely matching cases.\n"
            f"4. Answer in the requested language: {language}.\n"
        )
    elif weak_count > 0:
        system_prompt = (
            "You are Karnataka Crime GPT, an assistant specializing in analyzing Karnataka crime records.\n"
            "Your task is to provide ONLY a brief 1-2 sentence introduction stating that no exact search match was found, but related cases were found.\n\n"
            "CRITICAL RULES:\n"
            "1. Do NOT list individual FIR numbers or case bullets in your response — the case record list will be automatically formatted and appended by the system.\n"
            "2. State clearly: 'No exact search but related case:'\n"
            f"3. Answer in the requested language: {language}.\n"
        )
    else:
        system_prompt = (
            "You are Karnataka Crime GPT, an assistant specializing in analyzing Karnataka crime records.\n"
            "Your task is to state clearly in 1-2 sentences that no relevant cases in the system matched the specified MO pattern or criteria.\n"
            f"Answer in requested language: {language}.\n"
        )
    
    user_prompt = f"User Query: {message}\nTotal Strong Count in DB: {strong_count}\nReturned Count: {returned_count}"

    intro_narration = ""
    if openai_api_key:
        try:
            chat = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.1,
                openai_api_key=openai_api_key,
                max_retries=1
            )
            response = chat.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            intro_narration = response.content.strip()
        except Exception as e:
            logger.error(f"OpenAI Chat API failed: {e}")
            if strong_count > 0:
                intro_narration = f"Found {strong_count} cases closely matching '{message}':"
            elif weak_count > 0:
                intro_narration = f"No exact search but related case for '{message}':"
            else:
                intro_narration = f"No cases in the system matched the specified MO pattern for '{message}'."
    else:
        logger.warning("OPENAI_API_KEY not found. Using local fallback synthesis.")
        if strong_count > 0:
            intro_narration = f"Found {strong_count} cases closely matching '{message}':"
        elif weak_count > 0:
            intro_narration = f"No exact search but related case for '{message}':"
        else:
            intro_narration = f"No cases in the system matched the specified MO pattern for '{message}'."

    if case_list_markdown:
        final_answer = f"{intro_narration}\n\n{case_list_markdown}".strip()
    else:
        final_answer = intro_narration.strip()

    return {
        "answer": final_answer,
        "citations": citations
    }

def generate_fallback_synthesis(
    message: str, 
    retrieved_cases: list, 
    total_count: int = 0, 
    returned_count: int = 0, 
    offset: int = 0,
    language: str = "en",
    filters: dict = None
) -> str:
    """Generates a structured fallback response if the LLM fails or API Key is missing."""
    res = synthesize_answer(
        message, 
        retrieved_cases, 
        total_count=total_count, 
        returned_count=returned_count, 
        offset=offset,
        language=language,
        filters=filters
    )
    return res.get("answer", "")
