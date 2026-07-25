import datetime
import uuid
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Float, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from app.db import Base, DATABASE_URL

# Check database type
IS_POSTGRES = DATABASE_URL.startswith("postgresql")

if IS_POSTGRES:
    from pgvector.sqlalchemy import Vector
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    VectorType = Vector(1536)
    UUIDType = PG_UUID(as_uuid=True)
else:
    VectorType = JSON  # Fallback for SQLite
    UUIDType = String

# Association Tables
case_accused = Table(
    'case_accused',
    Base.metadata,
    Column('case_id', Integer, ForeignKey('fir_cases.id', ondelete='CASCADE'), primary_key=True),
    Column('accused_id', Integer, ForeignKey('accused.id', ondelete='CASCADE'), primary_key=True)
)

case_victims = Table(
    'case_victims',
    Base.metadata,
    Column('case_id', Integer, ForeignKey('fir_cases.id', ondelete='CASCADE'), primary_key=True),
    Column('victim_id', Integer, ForeignKey('victims.id', ondelete='CASCADE'), primary_key=True)
)

class District(Base):
    __tablename__ = 'districts'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)

    police_stations = relationship("PoliceStation", back_populates="district")
    locations = relationship("Location", back_populates="district")
    cases = relationship("FIRCase", back_populates="district")

class PoliceStation(Base):
    __tablename__ = 'police_stations'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    district_id = Column(Integer, ForeignKey('districts.id', ondelete='CASCADE'))

    district = relationship("District", back_populates="police_stations")
    cases = relationship("FIRCase", back_populates="police_station")

class Location(Base):
    __tablename__ = 'locations'
    id = Column(Integer, primary_key=True, index=True)
    address = Column(Text)
    city = Column(String(100))
    district_id = Column(Integer, ForeignKey('districts.id', ondelete='CASCADE'))
    latitude = Column(Float)
    longitude = Column(Float)

    district = relationship("District", back_populates="locations")
    cases = relationship("FIRCase", back_populates="location")

class Accused(Base):
    __tablename__ = 'accused'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    age = Column(Integer)
    gender = Column(String(20))
    phone = Column(String(20))
    address = Column(Text)
    photo_url = Column(Text)

    cases = relationship("FIRCase", secondary=case_accused, back_populates="accused")

class Victim(Base):
    __tablename__ = 'victims'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    age = Column(Integer)
    gender = Column(String(20))
    phone = Column(String(20))
    address = Column(Text)

    cases = relationship("FIRCase", secondary=case_victims, back_populates="victims")

class FIRCase(Base):
    __tablename__ = 'fir_cases'
    id = Column(Integer, primary_key=True, index=True)
    fir_number = Column(String(50), unique=True, nullable=False, index=True)
    crime_type = Column(String(100), nullable=False)
    ipc_sections = Column(String(200))
    district_id = Column(Integer, ForeignKey('districts.id'))
    police_station_id = Column(Integer, ForeignKey('police_stations.id'))
    location_id = Column(Integer, ForeignKey('locations.id'))
    date_reported = Column(Date, nullable=False)
    status = Column(String(30), default='under_investigation')
    mo_description = Column(Text)
    narrative = Column(Text)
    latitude = Column(Float)
    longitude = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    district = relationship("District", back_populates="cases")
    police_station = relationship("PoliceStation", back_populates="cases")
    location = relationship("Location", back_populates="cases")
    accused = relationship("Accused", secondary=case_accused, back_populates="cases")
    victims = relationship("Victim", secondary=case_victims, back_populates="cases")
    embedding = relationship("CaseEmbedding", uselist=False, back_populates="case")

class CaseEmbedding(Base):
    __tablename__ = 'case_embeddings'
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey('fir_cases.id', ondelete='CASCADE'), unique=True)
    content_text = Column(Text, nullable=False)
    embedding = Column(VectorType)

    case = relationship("FIRCase", back_populates="embedding")

class ChatSession(Base):
    __tablename__ = 'chat_sessions'
    id = Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()) if not IS_POSTGRES else uuid.uuid4())
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", backref="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(UUIDType, ForeignKey('chat_sessions.id', ondelete='CASCADE'))
    role = Column(String(20), nullable=False)  # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)  # JSON list of dicts
    visual_type = Column(String(30), nullable=True)  # 'network' | 'trend' | 'none'
    visual_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(30), nullable=False)  # 'investigator' | 'analyst' | 'supervisor' | 'policymaker'
    full_name = Column(String(150), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    username = Column(String(50), nullable=True)
    role = Column(String(30), nullable=True)
    method = Column(String(10), nullable=False)
    endpoint = Column(Text, nullable=False)
    status_code = Column(Integer, nullable=False)
    query_text = Column(Text, nullable=True)
    returned_records = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", backref="audit_logs")


