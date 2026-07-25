import pytest
from app.db import SessionLocal
from app.models import ChatSession, ChatMessage, User, AuditLog
from app.services.auth_service import create_access_token
from app.routers.chat import delete_session
from fastapi import HTTPException
import uuid

def test_delete_own_session_succeeds_and_creates_audit_log():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "investigator1").first()
        assert user is not None

        # Create dummy session and message
        sess = ChatSession(user_id=user.id)
        db.add(sess)
        db.commit()
        db.refresh(sess)

        msg = ChatMessage(session_id=sess.id, role="user", content="Test message to delete")
        db.add(msg)
        db.commit()

        session_id_str = str(sess.id)

        # Execute delete as investigator1
        current_user = {"id": user.id, "username": user.username, "role": user.role}
        res = delete_session(session_id=session_id_str, db=db, current_user=current_user)
        assert res["status"] == "success"

        # Verify DB records deleted
        deleted_sess = db.query(ChatSession).filter(ChatSession.id == sess.id).first()
        assert deleted_sess is None

        deleted_msg = db.query(ChatMessage).filter(ChatMessage.session_id == sess.id).first()
        assert deleted_msg is None

        # Verify Audit Log entry
        audit_log = db.query(AuditLog).filter(
            AuditLog.user_id == user.id,
            AuditLog.method == "DELETE",
            AuditLog.endpoint == f"/api/chat/sessions/{session_id_str}"
        ).order_by(AuditLog.created_at.desc()).first()
        assert audit_log is not None
        assert audit_log.status_code == 200
    finally:
        db.close()


def test_delete_other_user_session_returns_403_forbidden():
    db = SessionLocal()
    try:
        inv_user = db.query(User).filter(User.username == "investigator1").first()
        analyst_user = db.query(User).filter(User.username == "analyst1").first()
        assert inv_user is not None
        assert analyst_user is not None

        # Create session owned by investigator1
        sess = ChatSession(user_id=inv_user.id)
        db.add(sess)
        db.commit()
        db.refresh(sess)

        # Attempt to delete as analyst1
        current_user = {"id": analyst_user.id, "username": analyst_user.username, "role": analyst_user.role}
        with pytest.raises(HTTPException) as exc_info:
            delete_session(session_id=str(sess.id), db=db, current_user=current_user)

        assert exc_info.value.status_code == 403

        # Clean up session created by investigator1
        db.delete(sess)
        db.commit()
    finally:
        db.close()


def test_delete_nonexistent_session_returns_404_not_found():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "investigator1").first()
        fake_session_id = str(uuid.uuid4())
        current_user = {"id": user.id, "username": user.username, "role": user.role}

        with pytest.raises(HTTPException) as exc_info:
            delete_session(session_id=fake_session_id, db=db, current_user=current_user)

        assert exc_info.value.status_code == 404
    finally:
        db.close()
