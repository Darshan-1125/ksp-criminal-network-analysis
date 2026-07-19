import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import engine, Base
from app.routers import chat

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize database tables
logger.info("Initializing database schema...")
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Karnataka Crime GPT API", version="1.0.0")

# Setup CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Hackathon: allow all for ease of integration
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register chat router
app.include_router(chat.router)

# Import and register backend teammate routers if they exist, or stub them
try:
    from app.routers import cases, network, trends
    app.include_router(cases.router)
    app.include_router(network.router)
    app.include_router(trends.router)
    logger.info("Registered cases, network, and trends routers.")
except ImportError as e:
    logger.warning(f"Could not import backend teammate routers: {e}. Running in chat-only mode.")

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
