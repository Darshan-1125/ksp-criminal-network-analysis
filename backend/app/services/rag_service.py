import os
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

def synthesize_answer(message: str, retrieved_cases: list, language: str = "en") -> dict:
    """
    Synthesize retrieved records into a natural-language response.
    System prompt enforces citation of real fir_number.
    Returns:
      {
        "answer": str,
        "citations": [{"fir_number": str, "snippet": str}]
      }
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    # 1. Format the context
    context_lines = []
    for c in retrieved_cases:
        line = (
            f"FIR Number: {c.get('fir_number')}\n"
            f"Crime Type: {c.get('crime_type')}\n"
            f"IPC Sections: {c.get('ipc_sections')}\n"
            f"District: {c.get('district')}\n"
            f"Police Station: {c.get('police_station')}\n"
            f"Date Reported: {c.get('date_reported')}\n"
            f"Status: {c.get('status')}\n"
            f"MO Description: {c.get('mo_description')}\n"
            f"Narrative: {c.get('narrative', '')}\n"
            f"Accused: {', '.join([a.get('name', '') for a in c.get('accused', [])])}\n"
            f"Victims: {', '.join([v.get('name', '') for v in c.get('victims', [])])}\n"
            f"---"
        )
        context_lines.append(line)
    
    context_text = "\n".join(context_lines)
    
    if not context_text:
        context_text = "No cases found matching the criteria."

    # 2. Formulate prompts
    system_prompt = (
        "You are Karnataka Crime GPT, an assistant specializing in analyzing Karnataka crime records.\n"
        "Your task is to answer the user's query using the provided retrieved context.\n\n"
        "CRITICAL RULES:\n"
        "1. Every factual claim you make MUST cite the real fir_number from the context.\n"
        "2. Format citations clearly in your response (e.g., 'In case KA-2024-1123...').\n"
        "3. Do NOT invent or hallucinate any FIR numbers that are not present in the retrieved context.\n"
        "4. If no relevant records are found in the context, state that clearly instead of guessing.\n"
        f"5. Answer in the requested language: {language}.\n"
    )
    
    user_prompt = f"User Query: {message}\n\nRetrieved Context:\n{context_text}"
    
    answer = ""
    citations = []
    
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
            answer = response.content
        except Exception as e:
            logger.error(f"OpenAI Chat API failed: {e}")
            # Fallback to local synthesis
            answer = generate_fallback_synthesis(message, retrieved_cases, language)
    else:
        logger.warning("OPENAI_API_KEY not found. Using local fallback synthesis.")
        answer = generate_fallback_synthesis(message, retrieved_cases, language)

    # 3. Extract citations based on FIR numbers mentioned in the answer
    for c in retrieved_cases:
        fir = c.get('fir_number')
        if fir and fir in answer:
            # Avoid duplicate citations
            if not any(cit["fir_number"] == fir for cit in citations):
                snippet = c.get("mo_description") or c.get("narrative", "")[:200]
                citations.append({
                    "fir_number": fir,
                    "snippet": snippet
                })
                
    return {
        "answer": answer,
        "citations": citations
    }

def generate_fallback_synthesis(message: str, retrieved_cases: list, language: str = "en") -> str:
    """Generates a structured fallback response if the LLM fails or API Key is missing."""
    if not retrieved_cases:
        if language == "kn":
            return "ಯಾವುದೇ ಸಂಬಂಧಿತ ದಾಖಲೆಗಳು ಕಂಡುಬಂದಿಲ್ಲ."
        return "No relevant records were found in the system."
        
    lines = []
    if language == "kn":
        lines.append("ಕಂಡುಬಂದ ಪ್ರಕರಣಗಳ ವಿವರಗಳು ಕೆಳಗಿನಂತಿವೆ:")
        for c in retrieved_cases:
            acc_names = ", ".join([a.get('name', '') for a in c.get('accused', [])])
            lines.append(
                f"- ಎಫ್ಐಆರ್ ಸಂಖ್ಯೆ {c.get('fir_number')}: {c.get('district')} ಜಿಲ್ಲೆಯಲ್ಲಿ {c.get('crime_type')} ಪ್ರಕರಣ ದಾಖಲಾಗಿದೆ. "
                f"ಆರೋಪಿಗಳು: {acc_names or 'ಮಾಹಿತಿ ಇಲ್ಲ'}. ವಿವರ: {c.get('mo_description')}."
            )
        lines.append("\n(ಗಮನಿಸಿ: ಎಪಿಐ ದೋಷದ ಕಾರಣದಿಂದಾಗಿ ಈ ಪ್ರತ್ಯುತ್ತರವನ್ನು ಸಿಸ್ಟಮ್ ಸ್ವಯಂಚಾಲಿತವಾಗಿ ತಯಾರಿಸಿದೆ.)")
    else:
        lines.append("Here are the retrieved case details:")
        for c in retrieved_cases:
            acc_names = ", ".join([a.get('name', '') for a in c.get('accused', [])])
            lines.append(
                f"- FIR {c.get('fir_number')}: {c.get('crime_type')} reported in {c.get('district')} district. "
                f"Accused: {acc_names or 'N/A'}. Details: {c.get('mo_description')}."
            )
        lines.append("\n(Note: This is a fallback response compiled locally due to API rate limits or missing configuration.)")
        
    return "\n".join(lines)
