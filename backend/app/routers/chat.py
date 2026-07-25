import os
import uuid
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from langchain_openai import OpenAIEmbeddings

from app.db import get_db_session
from app.models import ChatSession, ChatMessage, FIRCase, CaseEmbedding, AuditLog
from app.services.langgraph_router import process_chat_message, clear_session_memory
from app.services.auth_service import require_role, redact_chat_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Pydantic Schemas
class ChatRequest(BaseModel):
    session_id: str
    message: str
    language: str = "en"
    offset: Optional[int] = 0

class Citation(BaseModel):
    fir_number: str
    snippet: str

class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: List[Citation]
    visual_type: str  # "network" | "trend" | "none"
    visual_payload: Optional[Any] = None
    total_count: Optional[int] = None
    returned_count: Optional[int] = None
    offset: Optional[int] = 0
    limit: Optional[int] = 15

class MessageHistoryItem(BaseModel):
    role: str
    content: str
    citations: Optional[List[Citation]] = None
    visual_type: Optional[str] = None
    visual_payload: Optional[Any] = None
    total_count: Optional[int] = None
    returned_count: Optional[int] = None
    offset: Optional[int] = None
    limit: Optional[int] = None
    created_at: str

class ChatHistoryResponse(BaseModel):
    messages: List[MessageHistoryItem]

class SessionResponse(BaseModel):
    session_id: str

class SessionSummaryItem(BaseModel):
    session_id: str
    created_at: str
    preview: str
    message_count: int
    visual_type: Optional[str] = "none"

class SessionListResponse(BaseModel):
    sessions: List[SessionSummaryItem]

class ReindexResponse(BaseModel):
    status: str
    count_indexed: int

class AuditLogItem(BaseModel):
    id: int
    username: Optional[str] = None
    role: Optional[str] = None
    method: str
    endpoint: str
    status_code: int
    query_text: Optional[str] = None
    returned_records: Optional[Any] = None
    created_at: str

class AuditLogsResponse(BaseModel):
    total: int
    results: List[AuditLogItem]

# Route implementations

ALL_CHAT_ROLES = ["admin", "supervisor", "investigator", "analyst", "policymaker", "read_only"]


@router.post("/chat/session", response_model=SessionResponse)
def create_session(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(ALL_CHAT_ROLES))
):
    """Create a new chat session linked to the current user and persist it to the database."""
    try:
        user_id = current_user.get("id")
        new_session = ChatSession(user_id=user_id)
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        return {"session_id": str(new_session.id)}
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        return {"session_id": str(uuid.uuid4())}

@router.get("/chat/sessions", response_model=SessionListResponse)
def get_user_sessions(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(ALL_CHAT_ROLES))
):
    """Retrieve all chat sessions belonging to the authenticated user."""
    try:
        user_id = current_user.get("id")
        sessions = db.query(ChatSession).filter(
            ChatSession.user_id == user_id
        ).order_by(ChatSession.created_at.desc()).all()

        results = []
        for s in sessions:
            first_user_msg = db.query(ChatMessage).filter(
                ChatMessage.session_id == s.id,
                ChatMessage.role == "user"
            ).order_by(ChatMessage.created_at.asc()).first()

            last_msg = db.query(ChatMessage).filter(
                ChatMessage.session_id == s.id
            ).order_by(ChatMessage.created_at.desc()).first()

            msg_count = db.query(ChatMessage).filter(
                ChatMessage.session_id == s.id
            ).count()

            preview = first_user_msg.content[:80] if first_user_msg else "New Conversation"
            visual_type = last_msg.visual_type if last_msg else "none"

            results.append({
                "session_id": str(s.id),
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "preview": preview,
                "message_count": msg_count,
                "visual_type": visual_type or "none"
            })
        return {"sessions": results}
    except Exception as e:
        logger.error(f"Failed to fetch user sessions: {e}")
        return {"sessions": []}

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    req: ChatRequest,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(ALL_CHAT_ROLES))
):
    """
    Core conversational endpoint.
    Retrieves answer via LangGraph, persists messages, and returns responses.
    Redacts response if current_user role is 'policymaker'.
    """
    session_id = req.session_id
    message = req.message
    language = req.language
    user_id = current_user.get("id")
    
    # 1. Parse/Verify UUID and Session Ownership
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        session_uuid = session_id

    try:
        session_obj = db.query(ChatSession).filter(ChatSession.id == session_uuid).first()
        if not session_obj:
            session_obj = ChatSession(id=session_uuid, user_id=user_id)
            db.add(session_obj)
            db.commit()
        elif session_obj.user_id is None:
            session_obj.user_id = user_id
            db.commit()
        elif session_obj.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied to session")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.warning(f"Could not verify/associate session in DB: {e}")

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
        db.rollback()
        logger.error(f"Failed to save user message: {e}")

    # 3. Process query using LangGraph Router
    offset = req.offset or 0
    result = process_chat_message(session_id, message, language, offset=offset)
    
    response_payload = {
        "session_id": session_id,
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "visual_type": result.get("visual_type", "none"),
        "visual_payload": result.get("visual_payload"),
        "total_count": result.get("total_count", 0),
        "returned_count": result.get("returned_count", 0),
        "offset": result.get("offset", offset),
        "limit": result.get("limit", 15)
    }

    # 4. Redaction rule for policymaker role
    if current_user.get("role") == "policymaker":
        response_payload = redact_chat_response(response_payload, db)

    # 5. Persist Assistant Response to DB
    try:
        saved_payload = response_payload["visual_payload"]
        meta = {
            "total_count": response_payload["total_count"],
            "returned_count": response_payload["returned_count"],
            "offset": response_payload["offset"],
            "limit": response_payload["limit"],
            "shown_count": (response_payload["offset"] or 0) + (response_payload["returned_count"] or 0)
        }
        if saved_payload is None:
            saved_payload = {"_meta": meta}
        elif isinstance(saved_payload, dict):
            saved_payload = dict(saved_payload)
            saved_payload["_meta"] = meta

        assistant_msg = ChatMessage(
            session_id=session_uuid,
            role="assistant",
            content=response_payload["answer"],
            citations=response_payload["citations"],
            visual_type=response_payload["visual_type"],
            visual_payload=saved_payload
        )
        db.add(assistant_msg)

        # 6. Log detailed audit log entry with query text and returned citations/records
        firs_returned = [c.get("fir_number") if isinstance(c, dict) else getattr(c, "fir_number", None) for c in (response_payload.get("citations") or [])]
        firs_returned = [f for f in firs_returned if f]
        
        audit_entry = AuditLog(
            user_id=current_user.get("id"),
            username=current_user.get("username"),
            role=current_user.get("role"),
            method="POST",
            endpoint="/api/chat",
            status_code=200,
            query_text=message,
            returned_records={
                "firs": firs_returned, 
                "visual_type": response_payload.get("visual_type"),
                "total_count": response_payload.get("total_count"),
                "returned_count": response_payload.get("returned_count")
            }
        )
        db.add(audit_entry)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save assistant message or audit log: {e}")

    return response_payload

@router.get("/chat/sessions/{session_id}/messages", response_model=ChatHistoryResponse)
@router.get("/chat/history/{session_id}", response_model=ChatHistoryResponse)
def get_chat_history(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(ALL_CHAT_ROLES))
):
    """Retrieve all messages for a session belonging to the logged-in user."""
    try:
        try:
            session_uuid = uuid.UUID(session_id)
        except ValueError:
            session_uuid = session_id

        # Verify session ownership if session exists
        session_obj = db.query(ChatSession).filter(ChatSession.id == session_uuid).first()
        if session_obj and session_obj.user_id is not None and session_obj.user_id != current_user.get("id"):
            raise HTTPException(status_code=403, detail="Access denied to session")

        messages = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_uuid
        ).order_by(ChatMessage.created_at.asc()).all()
        
        history = []
        for msg in messages:
            total_cnt = None
            ret_cnt = None
            off_val = None
            lim_val = None
            shown_cnt = None
            if isinstance(msg.visual_payload, dict) and "_meta" in msg.visual_payload:
                meta = msg.visual_payload["_meta"]
                total_cnt = meta.get("total_count")
                ret_cnt = meta.get("returned_count")
                off_val = meta.get("offset")
                lim_val = meta.get("limit")
                shown_cnt = meta.get("shown_count", (off_val or 0) + (ret_cnt or 0))

            history.append({
                "role": msg.role,
                "content": msg.content,
                "citations": msg.citations or [],
                "visual_type": msg.visual_type or "none",
                "visual_payload": msg.visual_payload,
                "total_count": total_cnt,
                "returned_count": ret_cnt,
                "shown_count": shown_cnt,
                "offset": off_val,
                "limit": lim_val,
                "created_at": msg.created_at.isoformat() if msg.created_at else ""
            })
        return {"messages": history}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch history for session {session_id}: {e}")
        return {"messages": []}

@router.delete("/chat/sessions/{session_id}")
def delete_session(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(ALL_CHAT_ROLES))
):
    """
    Deletes a chat session and all associated messages belonging to the current user.
    Verifies user ownership via JWT token and logs audit trail for law enforcement compliance.
    """
    try:
        try:
            session_uuid = uuid.UUID(session_id)
        except ValueError:
            session_uuid = session_id

        session_obj = db.query(ChatSession).filter(ChatSession.id == session_uuid).first()
        if not session_obj:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify session ownership
        if session_obj.user_id is not None and session_obj.user_id != current_user.get("id"):
            raise HTTPException(status_code=403, detail="Access denied to session")

        # Delete messages and session
        db.query(ChatMessage).filter(ChatMessage.session_id == session_uuid).delete()
        db.delete(session_obj)

        # Audit log entry for compliance
        audit_entry = AuditLog(
            user_id=current_user.get("id"),
            username=current_user.get("username"),
            role=current_user.get("role"),
            method="DELETE",
            endpoint=f"/api/chat/sessions/{session_id}",
            status_code=200,
            query_text=f"DELETED SESSION {session_id}",
            returned_records={"session_id": str(session_id), "action": "delete_session"}
        )
        db.add(audit_entry)
        db.commit()

        clear_session_memory(str(session_id))
        return {"status": "success", "message": f"Session '{session_id}' deleted."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")

@router.post("/embeddings/reindex", response_model=ReindexResponse)
def reindex_embeddings(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(["admin", "supervisor"]))
):
    """
    Loops all fir_cases, embeds narrative text, and upserts into case_embeddings.
    If OpenAI API is unavailable, inserts dummy embeddings.
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    cases = db.query(FIRCase).all()
    count_indexed = 0
    
    embeddings_model = None
    if openai_api_key:
        try:
            embeddings_model = OpenAIEmbeddings(openai_api_key=openai_api_key)
        except Exception as e:
            logger.error(f"Failed to initialize OpenAIEmbeddings: {e}")

    for case in cases:
        content_text = f"FIR: {case.fir_number}. Type: {case.crime_type}. MO: {case.mo_description}. Narrative: {case.narrative or ''}"
        
        embedding_vector = None
        if embeddings_model:
            try:
                embedding_vector = embeddings_model.embed_query(content_text)
            except Exception as e:
                logger.error(f"Failed to generate embedding for case {case.id}: {e}")
                embedding_vector = [0.0] * 1536
        else:
            embedding_vector = [0.0] * 1536
            
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

@router.get("/audit-logs", response_model=AuditLogsResponse)
def get_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_role(["admin", "supervisor"]))
):
    """Admin and Supervisor-only audit logs endpoint."""
    total = db.query(AuditLog).count()
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    
    results = []
    for log in logs:
        results.append({
            "id": log.id,
            "username": log.username,
            "role": log.role,
            "method": log.method,
            "endpoint": log.endpoint,
            "status_code": log.status_code,
            "query_text": log.query_text,
            "returned_records": log.returned_records,
            "created_at": log.created_at.isoformat() if log.created_at else ""
        })
        
    return {
        "total": total,
        "results": results
    }

