# Location: backend/scripts/seed_netskope_team.py
# Run: PYTHONPATH=. python scripts/seed_netskope_team.py

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import uuid, secrets
from datetime import datetime
from app.core.database import SessionLocal
from app.models.user import User, UserRole
from app.models.engineer import Engineer, AvailabilityStatus, SeniorityLevel
from app.models.team import Team, TeamMember, TeamMemberRole
from app.core.security import hash_password

db             = SessionLocal()
PASSWORD       = hash_password("Nexus@1234")
PLAIN_PASSWORD = "Nexus@1234"

def gen_engineer_id():
    while True:
        eid = f"ENG-{secrets.randbelow(9000)+1000}"
        if not db.query(Engineer).filter(Engineer.engineer_id == eid).first():
            return eid

def gen_team_id():
    while True:
        tid = f"TM-{secrets.randbelow(9000)+1000}"
        if not db.query(Team).filter(Team.team_id == tid).first():
            return tid

MANAGER = {
    "name":     "Priya Sharma",
    "email":    "mgr.netskope@nexusdesk.com",
    "city":     "Bangalore",
    "country":  "India",
    "timezone": "Asia/Kolkata",
}

ENGINEERS = [
    {"name": "Aditya Verma",    "email": "eng.netskope1@nexusdesk.com",  "city": "Bangalore",  "country": "India",         "timezone": "Asia/Kolkata",     "seniority": SeniorityLevel.SENIOR},
    {"name": "Sofia Esposito",  "email": "eng.netskope2@nexusdesk.com",  "city": "Rome",       "country": "Italy",         "timezone": "Europe/Rome",      "seniority": SeniorityLevel.SENIOR},
    {"name": "James Okonkwo",   "email": "eng.netskope3@nexusdesk.com",  "city": "Lagos",      "country": "Nigeria",       "timezone": "Africa/Lagos",     "seniority": SeniorityLevel.MID},
    {"name": "Chen Wei",        "email": "eng.netskope4@nexusdesk.com",  "city": "Beijing",    "country": "China",         "timezone": "Asia/Shanghai",    "seniority": SeniorityLevel.MID},
    {"name": "Sarah Mitchell",  "email": "eng.netskope5@nexusdesk.com",  "city": "Austin",     "country": "United States", "timezone": "America/Chicago",  "seniority": SeniorityLevel.SENIOR},
    {"name": "Ravi Krishnan",   "email": "eng.netskope6@nexusdesk.com",  "city": "Chennai",    "country": "India",         "timezone": "Asia/Kolkata",     "seniority": SeniorityLevel.MID},
    {"name": "Elena Novak",     "email": "eng.netskope7@nexusdesk.com",  "city": "Prague",     "country": "Czech Republic","timezone": "Europe/Prague",    "seniority": SeniorityLevel.MID},
    {"name": "Daniel Park",     "email": "eng.netskope8@nexusdesk.com",  "city": "Seoul",      "country": "South Korea",   "timezone": "Asia/Seoul",       "seniority": SeniorityLevel.SENIOR},
    {"name": "Amina Hassan",    "email": "eng.netskope9@nexusdesk.com",  "city": "Cairo",      "country": "Egypt",         "timezone": "Africa/Cairo",     "seniority": SeniorityLevel.MID},
    {"name": "Lucas Oliveira",  "email": "eng.netskope10@nexusdesk.com", "city": "Sao Paulo",  "country": "Brazil",        "timezone": "America/Sao_Paulo","seniority": SeniorityLevel.MID},
]

print("\n" + "─"*60)
print("STEP 1 — Manager")
print("─"*60)

existing_mgr = db.query(User).filter(User.email == MANAGER["email"]).first()
if existing_mgr:
    print(f"  ⚠ SKIP {MANAGER['email']} — already exists")
    mgr_user = existing_mgr
else:
    mgr_user = User(
        id=uuid.uuid4(), email=MANAGER["email"], full_name=MANAGER["name"],
        hashed_password=PASSWORD, role=UserRole.MANAGER,
        is_active=True, is_verified=True,
        city=MANAGER["city"], country=MANAGER["country"], timezone=MANAGER["timezone"],
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(mgr_user)
    db.flush()
    db.commit()
    print(f"  ✓ CREATE {MANAGER['name']} ({MANAGER['email']})")

print("\n" + "─"*60)
print("STEP 2 — Team")
print("─"*60)

existing_team = db.query(Team).filter(Team.name == "Netskope & Cloud Security").first()
if existing_team:
    print(f"  ⚠ SKIP — already exists ({existing_team.team_id})")
    team = existing_team
else:
    team = Team(
        id=uuid.uuid4(), team_id=gen_team_id(),
        name="Netskope & Cloud Security",
        description="Manages Netskope gateway, cloud proxy, and secure web access",
        domain_focus=["security", "networking"],
        region="Global", timezone="Asia/Kolkata",
        manager_id=mgr_user.id, is_active=True,
        max_ticket_capacity=30, active_ticket_count=0,
        total_resolved=0, avg_resolution_time=0, sla_compliance_rate=100,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(team)
    db.flush()
    db.commit()
    print(f"  ✓ CREATE Netskope & Cloud Security ({team.team_id})")

print("\n" + "─"*60)
print("STEP 3 — Engineers")
print("─"*60)

created = skipped = 0
for eng in ENGINEERS:
    existing_user = db.query(User).filter(User.email == eng["email"]).first()
    if existing_user:
        # Ensure team membership exists
        already = db.query(TeamMember).filter(
            TeamMember.team_id == team.id,
            TeamMember.user_id == existing_user.id,
        ).first()
        if not already:
            db.add(TeamMember(id=uuid.uuid4(), team_id=team.id,
                user_id=existing_user.id, role_in_team=TeamMemberRole.MEMBER,
                joined_at=datetime.utcnow()))
            db.commit()
        print(f"  ⚠ SKIP {eng['name']:25s} ({eng['email']})")
        skipped += 1
        continue

    user = User(
        id=uuid.uuid4(), email=eng["email"], full_name=eng["name"],
        hashed_password=PASSWORD, role=UserRole.ENGINEER,
        is_active=True, is_verified=True,
        city=eng["city"], country=eng["country"], timezone=eng["timezone"],
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.flush()

    engineer = Engineer(
        id=uuid.uuid4(), user_id=user.id, engineer_id=gen_engineer_id(),
        domain_expertise=["security", "networking"],
        region=eng["city"], timezone=eng["timezone"],
        seniority_level=eng["seniority"],
        max_ticket_capacity=10, availability_status=AvailabilityStatus.AVAILABLE,
        active_ticket_count=0, is_activated=True, temp_password_hash=None,
        total_resolved=0, avg_resolution_time=60, sla_compliance_rate=100,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(engineer)
    db.flush()

    db.add(TeamMember(id=uuid.uuid4(), team_id=team.id, user_id=user.id,
        role_in_team=TeamMemberRole.MEMBER, joined_at=datetime.utcnow()))
    db.commit()
    created += 1
    print(f"  ✓ CREATE {eng['name']:25s} | {eng['email']:38s} | {eng['city']}")

print("\n" + "═"*60)
print("SEED COMPLETE")
print("═"*60)
print(f"  Manager:   mgr.netskope@nexusdesk.com")
print(f"  Team:      Netskope & Cloud Security ({team.team_id})")
print(f"  Engineers: created={created} skipped={skipped}")
print(f"  Password:  {PLAIN_PASSWORD}")
print("═"*60)
db.close()