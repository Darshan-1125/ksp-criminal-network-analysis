import os
import uuid
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from langchain_openai import OpenAIEmbeddings

from app.db import get_db_session
from app.models import ChatSession, ChatMessage, FIRCase, CaseEmbedding
from app.services.langgraph_router import process_chat_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Pydantic Schemas
class ChatRequest(BaseModel):
    session_id: str
    message: str
    language: str = "en"

class Citation(BaseModel):
    fir_number: str
    snippet: str

class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: List[Citation]
    visual_type: str  # "network" | "trend" | "none"
    visual_payload: Optional[Any] = None

class MessageHistoryItem(BaseModel):
    role: str
    content: str
    citations: Optional[List[Citation]] = None
    visual_type: Optional[str] = None
    visual_payload: Optional[Any] = None
    created_at: str

class ChatHistoryResponse(BaseModel):
    messages: List[MessageHistoryItem]

class SessionResponse(BaseModel):
    session_id: str

class ReindexResponse(BaseModel):
    status: str
    count_indexed: int

# Route implementations

@router.post("/chat/session", response_model=SessionResponse)
def create_session(db: Session = Depends(get_db_session)):
    """Create a new chat session and persist it to the database."""
    try:
        new_session = ChatSession()
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        return {"session_id": str(new_session.id)}
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        # Fallback in case of DB issue (return fresh uuid)
        return {"session_id": str(uuid.uuid4())}

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest, db: Session = Depends(get_db_session)):
    """
    Core conversational endpoint.
    Retrieves answer via LangGraph, persists messages, and returns responses.
    """
    session_id = req.session_id
    message = req.message
    language = req.language
    
    # 1. Parse/Verify UUID
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        # Fallback to string representation if using SQLite
        session_uuid = session_id

    # 2. Persist User Message to DB
    try:
        user_msg = ChatMessage(
            session_id=session_uuid,
            role="user",
            content=message,
            citations=None,
            visual_type=None,
            visual_payload=None
        )
        db.add(user_msg)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save user message: {e}")
        # Continue so we don't break the conversation on DB insert issues

    # 3. Process the query using LangGraph Router
    result = process_chat_message(session_id, message, language)
    
    answer = result.get("answer", "")
    citations = result.get("citations", [])
    visual_type = result.get("visual_type", "none")
    visual_payload = result.get("visual_payload")

    # 4. Persist Assistant Response to DB
    try:
        assistant_msg = ChatMessage(
            session_id=session_uuid,
            role="assistant",
            content=answer,
            citations=citations,
            visual_type=visual_type,
            visual_payload=visual_payload
        )
        db.add(assistant_msg)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save assistant message: {e}")

    return {
        "session_id": session_id,
        "answer": answer,
        "citations": citations,
        "visual_type": visual_type,
        "visual_payload": visual_payload
    }

@router.get("/chat/history/{session_id}", response_model=ChatHistoryResponse)
def get_chat_history(session_id: str, db: Session = Depends(get_db_session)):
    """Retrieve all messages for a session ordered by created_at."""
    try:
        # Parse UUID if possible
        try:
            session_uuid = uuid.UUID(session_id)
        except ValueError:
            session_uuid = session_id

        messages = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_uuid
        ).order_by(ChatMessage.created_at.asc()).all()
        
        history = []
        for msg in messages:
            history.append({
                "role": msg.role,
                "content": msg.content,
                "citations": msg.citations or [],
                "visual_type": msg.visual_type or "none",
                "visual_payload": msg.visual_payload,
                "created_at": msg.created_at.isoformat() if msg.created_at else ""
            })
        return {"messages": history}
    except Exception as e:
        logger.error(f"Failed to fetch history for session {session_id}: {e}")
        return {"messages": []}

@router.post("/embeddings/reindex", response_model=ReindexResponse)
def reindex_embeddings(db: Session = Depends(get_db_session)):
    """
    Loops all fir_cases, embeds narrative text, and upserts into case_embeddings.
    If OpenAI API is unavailable, inserts dummy embeddings.
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    cases = db.query(FIRCase).all()
    count_indexed = 0
    
    # Initialize Embeddings if key is present
    embeddings_model = None
    if openai_api_key:
        try:
            embeddings_model = OpenAIEmbeddings(openai_api_key=openai_api_key)
        except Exception as e:
            logger.error(f"Failed to initialize OpenAIEmbeddings: {e}")

    for case in cases:
        content_text = f"FIR: {case.fir_number}. Type: {case.crime_type}. MO: {case.mo_description}. Narrative: {case.narrative or ''}"
        
        # Create embedding vector (1536 float elements)
        embedding_vector = None
        if embeddings_model:
            try:
                embedding_vector = embeddings_model.embed_query(content_text)
            except Exception as e:
                logger.error(f"Failed to generate embedding for case {case.id}: {e}")
                # Fallback to dummy vector
                embedding_vector = [0.0] * 1536
        else:
            # Fallback to dummy vector
            embedding_vector = [0.0] * 1536
            
        # Check if already exists
        existing = db.query(CaseEmbedding).filter(CaseEmbedding.case_id == case.id).first()
        if existing:
            existing.content_text = content_text
            existing.embedding = embedding_vector
        else:
            new_emb = CaseEmbedding(
                case_id=case.id,
                content_text=content_text,
                embedding=embedding_vector
            )
            db.add(new_emb)
            
        count_indexed += 1

    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit reindexed embeddings: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Database commit failed during reindexing")
        
    return {"status": "ok", "count_indexed": count_indexed}
