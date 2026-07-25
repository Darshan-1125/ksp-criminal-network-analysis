import sys
import os
from passlib.context import CryptContext

# Adjust sys.path to backend directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.db import engine, SessionLocal, Base
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_USERS = [
    {
        "username": "admin1",
        "password": "admin_pass123",
        "role": "admin",
        "full_name": "System Administrator Officer"
    },
    {
        "username": "investigator1",
        "password": "investigator_pass123",
        "role": "investigator",
        "full_name": "Inspector Rajesh Kumar"
    },
    {
        "username": "analyst1",
        "password": "analyst_pass123",
        "role": "analyst",
        "full_name": "Senior Analyst Priya Sharma"
    },
    {
        "username": "supervisor1",
        "password": "supervisor_pass123",
        "role": "supervisor",
        "full_name": "Superintendent Ananth Rao"
    },
    {
        "username": "policymaker1",
        "password": "policymaker_pass123",
        "role": "policymaker",
        "full_name": "Policy Director Sunita Patil"
    },
    {
        "username": "readonly1",
        "password": "readonly_pass123",
        "role": "read_only",
        "full_name": "Auditor Read-Only Officer"
    }
]

def seed_users():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("=" * 60)
        print("SEEDING DEMO USERS FOR KARNATAKA CRIME GPT")
        print("=" * 60)
        
        for user_data in DEMO_USERS:
            existing = db.query(User).filter(User.username == user_data["username"]).first()
            hashed_pwd = pwd_context.hash(user_data["password"])
            if existing:
                existing.password_hash = hashed_pwd
                existing.role = user_data["role"]
                existing.full_name = user_data["full_name"]
                print(f"[UPDATED] User: {user_data['username']} | Role: {user_data['role']} | Password: {user_data['password']}")
            else:
                user = User(
                    username=user_data["username"],
                    password_hash=hashed_pwd,
                    role=user_data["role"],
                    full_name=user_data["full_name"]
                )
                db.add(user)
                print(f"[CREATED] User: {user_data['username']} | Role: {user_data['role']} | Password: {user_data['password']}")
        
        db.commit()
        print("=" * 60)
        print("User seeding completed successfully.")
        print("=" * 60)
    except Exception as e:
        db.rollback()
        print(f"Error seeding users: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_users()
