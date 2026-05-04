# backend/seed_10_engineers.py
# Run: python seed_10_engineers.py

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal
from app.models.user import User, UserRole
from app.models.engineer import Engineer, AvailabilityStatus
from app.core.security import hash_password

import uuid
from datetime import datetime

db = SessionLocal()

PASSWORD = hash_password("UBAID123@")

ENGINEERS = [
    # DevOps
    {"name": "Ryan OConnor",  "email": "ryan.oconnor@nexusdesk.com",  "domain": "devops",  "city": "Boston",      "country": "United States", "tz": "America/New_York"},
    {"name": "Nina Petrov",   "email": "nina.petrov@nexusdesk.com",   "domain": "devops",  "city": "Berlin",      "country": "Germany",       "tz": "Europe/Berlin"},

    # Database
    {"name": "Arjun Mehta",   "email": "arjun.mehta@nexusdesk.com",   "domain": "database","city": "Hyderabad",   "country": "India",         "tz": "Asia/Kolkata"},
    {"name": "Mason Taylor", "email": "mason.taylor@nexusdesk.com", "domain": "database","city": "Boston",      "country": "United States", "tz": "America/New_York"},

    # Networking
    {"name": "Liam Carter",   "email": "liam.carter@nexusdesk.com",   "domain": "networking","city": "New York", "country": "United States", "tz": "America/New_York"},
    {"name": "Aisha Rahman",  "email": "aisha.rahman@nexusdesk.com",  "domain": "networking","city": "Dubai",    "country": "UAE",           "tz": "Asia/Dubai"},

    # Security
    {"name": "Raj Sharma",    "email": "raj.sharma@nexusdesk.com",    "domain": "security","city": "Mumbai",      "country": "India",         "tz": "Asia/Kolkata"},
    {"name": "Emma Wilson",   "email": "emma.wilson@nexusdesk.com",   "domain": "security","city": "Chicago",     "country": "United States", "tz": "America/Chicago"},

    # Software
    {"name": "Ava Thompson",  "email": "ava.thompson@nexusdesk.com",  "domain": "software","city": "San Francisco","country": "United States","tz": "America/Los_Angeles"},
    {"name": "Omar Khalid",   "email": "omar.khalid@nexusdesk.com",   "domain": "software","city": "Cairo",       "country": "Egypt",         "tz": "Africa/Cairo"},
]

print(f"Creating {len(ENGINEERS)} engineers...")
created = 0
skipped = 0

for eng in ENGINEERS:
    existing = db.query(User).filter(User.email == eng["email"]).first()
    if existing:
        skipped += 1
        print(f"  ⚠ SKIP  {eng['name']:25s} (already exists)")
        continue

    user = User(
        id=uuid.uuid4(),
        email=eng["email"],
        full_name=eng["name"],
        hashed_password=PASSWORD,
        role=UserRole.ENGINEER,
        is_active=True,
        is_verified=True,
        city=eng["city"],
        country=eng["country"],
        timezone=eng["tz"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.flush()

    engineer = Engineer(
        user_id=user.id,
        engineer_id=f"ENG-{str(uuid.uuid4())[:8]}",
        domain_expertise=[eng["domain"]],
        region=eng["city"],
        timezone=eng["tz"],
        max_ticket_capacity=10,
        availability_status=AvailabilityStatus.AVAILABLE,
        active_ticket_count=0,
        is_activated=True,
        avg_resolution_time=60,
    )

    db.add(engineer)
    created += 1

    print(f"  ✓ {eng['name']:25s} | {eng['domain']:15s} | {eng['city']}, {eng['country']}")

db.commit()
db.close()

print(f"\n✅ Done! Created: {created} | Skipped: {skipped}")
print("Password for all: UBAID123@")