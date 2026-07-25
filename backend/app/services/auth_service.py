import os
import re
import datetime
from typing import List, Optional, Dict, Any
import jwt
import bcrypt

# Fix passlib compatibility issue with bcrypt >= 4.0.0 in Python 3.12+
if not hasattr(bcrypt, "__about__"):
    class BcryptAbout:
        __version__ = getattr(bcrypt, "__version__", "4.0.0")
    bcrypt.__about__ = BcryptAbout()

_orig_hashpw = bcrypt.hashpw
def _safe_hashpw(password, salt):
    if isinstance(password, bytes) and len(password) > 72:
        password = password[:72]
    elif isinstance(password, str) and len(password) > 72:
        password = password[:72]
    return _orig_hashpw(password, salt)
bcrypt.hashpw = _safe_hashpw

from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.models import User, Accused, Victim

# Crypt context for hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "karnataka_crime_gpt_secret_key_2026_hackathon")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Defined Role Constants
ROLE_ADMIN = "admin"
ROLE_SUPERVISOR = "supervisor"
ROLE_INVESTIGATOR = "investigator"
ROLE_ANALYST = "analyst"
ROLE_POLICYMAKER = "policymaker"
ROLE_READ_ONLY = "read_only"

ALL_ROLES = [ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_INVESTIGATOR, ROLE_ANALYST, ROLE_POLICYMAKER, ROLE_READ_ONLY]
FULL_ACCESS_ROLES = [ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_INVESTIGATOR, ROLE_ANALYST]
CASES_ROLES = [ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_INVESTIGATOR, ROLE_ANALYST, ROLE_READ_ONLY]
NETWORK_ROLES = [ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_INVESTIGATOR, ROLE_ANALYST]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password[:72], hashed_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password[:72])

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "token_type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "token_type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") and payload.get("token_type") != "access":
            return None
        return payload
    except Exception:
        return None

def decode_refresh_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "refresh":
            return None
        return payload
    except Exception:
        return None


def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db_session)) -> dict:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: str = payload.get("sub")
    role: str = payload.get("role")
    if not username or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "full_name": user.full_name
    }

def get_optional_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db_session)) -> Optional[dict]:
    """Helper for audit middleware/logging when token might be missing/invalid."""
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "full_name": user.full_name
    }

def require_role(allowed_roles: List[str]):
    """FastAPI dependency factory for role checking."""
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions"
            )
        return current_user
    return role_checker

def redact_chat_response(chat_response: dict, db: Session) -> dict:
    """
    Redaction for policymaker role:
    Strips accused/victim names, phone numbers, and addresses from 'answer' and 'citations'.
    Keeps fir_number, crime_type, district, date, and aggregate counts.
    """
    answer = chat_response.get("answer", "")
    citations = chat_response.get("citations", [])

    # 1. Fetch names, phones, addresses of all accused and victims from DB to redact
    accused_list = db.query(Accused).all()
    victim_list = db.query(Victim).all()

    sensitive_tokens = set()
    for acc in accused_list:
        if acc.name and len(acc.name.strip()) > 2:
            sensitive_tokens.add(acc.name.strip())
        if acc.phone:
            sensitive_tokens.add(acc.phone.strip())
        if acc.address and len(acc.address.strip()) > 3:
            sensitive_tokens.add(acc.address.strip())
            
    for vic in victim_list:
        if vic.name and len(vic.name.strip()) > 2:
            sensitive_tokens.add(vic.name.strip())
        if vic.phone:
            sensitive_tokens.add(vic.phone.strip())
        if vic.address and len(vic.address.strip()) > 3:
            sensitive_tokens.add(vic.address.strip())

    # Sort sensitive tokens by length descending so longer phrases get replaced first
    sorted_tokens = sorted(sensitive_tokens, key=len, reverse=True)

    redacted_answer = answer
    for token in sorted_tokens:
        if token in redacted_answer:
            redacted_answer = redacted_answer.replace(token, "[REDACTED]")

    # Additional regex for 10-digit phone numbers and generic phone patterns
    redacted_answer = re.sub(r'\b\+?\d[0-9\s\-]{8,12}\d\b', '[REDACTED PHONE]', redacted_answer)

    # Process citations array
    redacted_citations = []
    for cit in citations:
        cit_dict = cit if isinstance(cit, dict) else cit.dict()
        snippet = cit_dict.get("snippet", "")
        for token in sorted_tokens:
            if token in snippet:
                snippet = snippet.replace(token, "[REDACTED]")
        snippet = re.sub(r'\b\+?\d[0-9\s\-]{8,12}\d\b', '[REDACTED PHONE]', snippet)
        cit_dict["snippet"] = snippet
        redacted_citations.append(cit_dict)

    new_response = dict(chat_response)
    new_response["answer"] = redacted_answer
    new_response["citations"] = redacted_citations

    return new_response
