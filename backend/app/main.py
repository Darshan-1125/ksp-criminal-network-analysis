import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text
from app.db import engine, Base, SessionLocal
from app.models import User, AuditLog
from app.services.auth_service import decode_access_token
from app.routers import auth, chat, cases, network, trends

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize database schema & apply column migrations
logger.info("Initializing database schema...")
Base.metadata.create_all(bind=engine)

try:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;"))
except Exception as e:
    logger.warning(f"Schema migration check for chat_sessions.user_id: {e}")

app = FastAPI(title="Karnataka Crime GPT API", version="1.0.0")

origins = [
    "http://localhost:5173",
    "https://YOUR_PROJECT.vercel.app",
]
# Setup CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Audit Middleware
@app.middleware("http")
async def audit_log_middleware(request: Request, call_next):
    response = await call_next(request)
    
    path = request.url.path
    # Intercept all /api/* routes (excluding CORS OPTIONS pre-flights for cleanliness)
    if path.startswith("/api") and request.method != "OPTIONS":
        try:
            auth_header = request.headers.get("authorization")
            user_id = None
            username = None
            role = None
            
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]
                payload = decode_access_token(token)
                if payload:
                    username = payload.get("sub")
                    role = payload.get("role")
                    
                    db = SessionLocal()
                    try:
                        u = db.query(User).filter(User.username == username).first()
                        if u:
                            user_id = u.id
                    finally:
                        db.close()

            db = SessionLocal()
            try:
                log_entry = AuditLog(
                    user_id=user_id,
                    username=username,
                    role=role,
                    method=request.method,
                    endpoint=path,
                    status_code=response.status_code
                )
                db.add(log_entry)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Audit log writing failed: {e}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error in audit middleware: {e}")
            
    return response

# Register routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(cases.router)
app.include_router(network.router)
app.include_router(trends.router)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
