# File: backend/seed_demo.py
# Run: python seed_demo.py
# Creates 7 demo users + 18 engineers for demo scenarios

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

# ── 7 DEMO USERS ────────────────────────────────────────────────────────────
USERS = [
    {"name": "Ahmed Al-Farsi",   "email": "ahmed.user@nexusdesk.com",    "city": "Dubai",      "country": "UAE",           "tz": "Asia/Dubai"},
    {"name": "Yuki Sato",        "email": "yuki.user@nexusdesk.com",     "city": "Tokyo",      "country": "Japan",         "tz": "Asia/Tokyo"},
    {"name": "James Crawford",   "email": "james.user@nexusdesk.com",    "city": "Sydney",     "country": "Australia",     "tz": "Australia/Sydney"},
    {"name": "Sarah Mitchell",   "email": "sarah.user@nexusdesk.com",    "city": "New York",   "country": "United States", "tz": "America/New_York"},
    {"name": "Oliver Bennett",   "email": "oliver.user@nexusdesk.com",   "city": "London",     "country": "United Kingdom","tz": "Europe/London"},
    {"name": "Priya Sharma",     "email": "priya.user@nexusdesk.com",    "city": "Mumbai",     "country": "India",         "tz": "Asia/Kolkata"},
    {"name": "Grace Wanjiku",    "email": "grace.user@nexusdesk.com",    "city": "Nairobi",    "country": "Kenya",         "tz": "Africa/Nairobi"},
]

# ── 18 DEMO ENGINEERS ────────────────────────────────────────────────────────
# Carefully chosen to demonstrate all 7 routing scenarios
ENGINEERS = [
    # Networking — covers Dubai(perfect), New York(timezone), London(cross-continent)
    {"name": "Aisha Rahman",     "email": "aisha.rahman@nexusdesk.com",     "domain": "networking", "city": "Dubai",      "country": "UAE",           "tz": "Asia/Dubai"},
    {"name": "Liam Carter",      "email": "liam.carter@nexusdesk.com",      "domain": "networking", "city": "New York",   "country": "United States", "tz": "America/New_York"},
    {"name": "James Patel",      "email": "james.patel@nexusdesk.com",      "domain": "networking", "city": "London",     "country": "United Kingdom","tz": "Europe/London"},

    # Security — covers Tokyo(perfect), Mumbai(nearest)
    {"name": "Yuki Tanaka",      "email": "yuki.tanaka@nexusdesk.com",      "domain": "security",   "city": "Tokyo",      "country": "Japan",         "tz": "Asia/Tokyo"},
    {"name": "Raj Sharma",       "email": "raj.sharma@nexusdesk.com",       "domain": "security",   "city": "Mumbai",     "country": "India",         "tz": "Asia/Kolkata"},
    {"name": "Emma Wilson",      "email": "emma.wilson@nexusdesk.com",      "domain": "security",   "city": "Chicago",    "country": "United States", "tz": "America/Chicago"},

    # Cloud — covers London(cross-continent→Paris), Nairobi(perfect)
    {"name": "Lucas Dubois",     "email": "lucas.dubois@nexusdesk.com",     "domain": "cloud",      "city": "Paris",      "country": "France",        "tz": "Europe/Paris"},
    {"name": "Amara Osei",       "email": "amara.osei@nexusdesk.com",       "domain": "cloud",      "city": "Nairobi",    "country": "Kenya",         "tz": "Africa/Nairobi"},
    {"name": "Olivia Chen",      "email": "olivia.chen@nexusdesk.com",      "domain": "cloud",      "city": "Seattle",    "country": "United States", "tz": "America/Los_Angeles"},

    # DevOps — covers Sydney(no exact→Tokyo nearest)
    {"name": "Aiko Suzuki",      "email": "aiko.suzuki@nexusdesk.com",      "domain": "devops",     "city": "Tokyo",      "country": "Japan",         "tz": "Asia/Tokyo"},
    {"name": "Tom Harrison",     "email": "tom.harrison@nexusdesk.com",     "domain": "devops",     "city": "Manchester", "country": "United Kingdom","tz": "Europe/London"},
    {"name": "Aryan Patel",      "email": "aryan.patel@nexusdesk.com",      "domain": "devops",     "city": "Pune",       "country": "India",         "tz": "Asia/Kolkata"},

    # Hardware — for workload balancing demo
    {"name": "Ethan Brooks",     "email": "ethan.brooks@nexusdesk.com",     "domain": "hardware",   "city": "Austin",     "country": "United States", "tz": "America/Chicago"},
    {"name": "Sara Johansson",   "email": "sara.johansson@nexusdesk.com",   "domain": "hardware",   "city": "Stockholm",  "country": "Sweden",        "tz": "Europe/Stockholm"},

    # Database — for mixed scenario
    {"name": "Arjun Mehta",      "email": "arjun.mehta@nexusdesk.com",      "domain": "database",   "city": "Hyderabad",  "country": "India",         "tz": "Asia/Kolkata"},
    {"name": "Mason Taylor",     "email": "mason.taylor@nexusdesk.com",     "domain": "database",   "city": "Boston",     "country": "United States", "tz": "America/New_York"},

    # Infrastructure + Identity — extra coverage
    {"name": "Grace Lee",        "email": "grace.lee@nexusdesk.com",        "domain": "infrastructure", "city": "Dallas", "country": "United States", "tz": "America/Chicago"},
    {"name": "Jack Murphy",      "email": "jack.murphy@nexusdesk.com",      "domain": "identity_access","city": "Denver", "country": "United States", "tz": "America/Denver"},
]

print("=" * 60)
print("NexusDesk Demo Seeder")
print("=" * 60)

# ── Create Users ─────────────────────────────────────────────────────────────
print(f"\n📦 Creating {len(USERS)} demo users...")
users_created = 0
for u in USERS:
    existing = db.query(User).filter(User.email == u["email"]).first()
    if existing:
        print(f"  ⚠ SKIP  {u['name']:20s} (already exists)")
        continue
    user = User(
        id=uuid.uuid4(),
        email=u["email"],
        full_name=u["name"],
        hashed_password=PASSWORD,
        role=UserRole.USER,
        is_active=True,
        is_verified=True,
        city=u["city"],
        country=u["country"],
        timezone=u["tz"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    users_created += 1
    print(f"  ✓ {u['name']:20s} | {u['city']:12s} | {u['country']}")

# ── Create Engineers ──────────────────────────────────────────────────────────
print(f"\n🔧 Creating {len(ENGINEERS)} demo engineers...")
engs_created = 0
for eng in ENGINEERS:
    existing = db.query(User).filter(User.email == eng["email"]).first()
    if existing:
        print(f"  ⚠ SKIP  {eng['name']:20s} (already exists)")
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
        engineer_id=f"ENG-{str(uuid.uuid4())[:8].upper()}",
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
    engs_created += 1
    print(f"  ✓ {eng['name']:20s} | {eng['domain']:18s} | {eng['city']}, {eng['country']}")

db.commit()
db.close()

print(f"\n{'=' * 60}")
print(f"✅ Done!")
print(f"   Users created   : {users_created}")
print(f"   Engineers created: {engs_created}")
print(f"\n📋 Demo User Logins (password: UBAID123@):")
for u in USERS:
    print(f"   {u['email']:35s} → {u['city']}, {u['country']}")
print(f"\n🎯 Scenarios ready:")
print(f"   1. Ahmed (Dubai)    → Networking → Aisha Rahman (Dubai) ✓ Perfect")
print(f"   2. Yuki (Tokyo)     → Security   → Yuki Tanaka (Tokyo)  ✓ Perfect")
print(f"   3. James (Sydney)   → DevOps     → Aiko Suzuki (Tokyo)  ✓ Nearest TZ")
print(f"   4. Sarah (New York) → Networking → Liam Carter (NY)     ✓ Same city")
print(f"   5. Oliver (London)  → Cloud      → Lucas Dubois (Paris) ✓ Cross-border")
print(f"   6. Priya (Mumbai)   → Security   → Raj Sharma (Mumbai)  ✓ Perfect")
print(f"   7. Grace (Nairobi)  → Cloud      → Amara Osei (Nairobi) ✓ Perfect")