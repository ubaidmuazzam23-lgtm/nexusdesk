# backend/scripts/seed_7_teams.py
#
# PURPOSE:
#   Seeds 7 teams + 7 managers + 21 engineers (3 per team)
#   All emails match exactly what is in enterprise_full_domain_registry_v2.csv
#
# RUN:
#   cd backend
#   PYTHONPATH=. python scripts/seed_7_teams.py
#
# PASSWORD FOR ALL: Nexus@1234

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import uuid
import secrets
from datetime import datetime

from app.core.database import SessionLocal
from app.models.user import User, UserRole
from app.models.engineer import Engineer, AvailabilityStatus, SeniorityLevel
from app.models.team import Team, TeamMember, TeamMemberRole
from app.core.security import hash_password

db = SessionLocal()
PASSWORD       = hash_password("Nexus@1234")
PLAIN_PASSWORD = "Nexus@1234"


def gen_engineer_id() -> str:
    while True:
        eid = f"ENG-{secrets.randbelow(9000) + 1000}"
        if not db.query(Engineer).filter(Engineer.engineer_id == eid).first():
            return eid

def gen_team_id() -> str:
    while True:
        tid = f"TM-{secrets.randbelow(9000) + 1000}"
        if not db.query(Team).filter(Team.team_id == tid).first():
            return tid


# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────

MANAGERS = [
    {
        "name":     "Sarah Mitchell",
        "email":    "mgr.netops@nexusdesk.com",
        "city":     "Mumbai",
        "country":  "India",
        "timezone": "Asia/Kolkata",
        "team_key": "netops",
    },
    {
        "name":     "Daniel Okafor",
        "email":    "mgr.cloud@nexusdesk.com",
        "city":     "Singapore",
        "country":  "Singapore",
        "timezone": "Asia/Singapore",
        "team_key": "cloud",
    },
    {
        "name":     "Priya Nair",
        "email":    "mgr.dba@nexusdesk.com",
        "city":     "Hyderabad",
        "country":  "India",
        "timezone": "Asia/Kolkata",
        "team_key": "dba",
    },
    {
        "name":     "Marcus Webb",
        "email":    "mgr.devops@nexusdesk.com",
        "city":     "Berlin",
        "country":  "Germany",
        "timezone": "Europe/Berlin",
        "team_key": "devops",
    },
    {
        "name":     "Fatima Al-Rashid",
        "email":    "mgr.hardware@nexusdesk.com",
        "city":     "Dubai",
        "country":  "UAE",
        "timezone": "Asia/Dubai",
        "team_key": "hardware",
    },
    {
        "name":     "James Thornton",
        "email":    "mgr.security@nexusdesk.com",
        "city":     "London",
        "country":  "United Kingdom",
        "timezone": "Europe/London",
        "team_key": "security",
    },
    {
        "name":     "Mei Lin",
        "email":    "mgr.erp@nexusdesk.com",
        "city":     "Shanghai",
        "country":  "China",
        "timezone": "Asia/Shanghai",
        "team_key": "erp",
    },
]

TEAMS = [
    {
        "key":          "netops",
        "name":         "Network Operations",
        "description":  "Manages all networking infrastructure, identity & access management",
        "domain_focus": ["networking", "identity_access"],
        "region":       "India",
        "timezone":     "Asia/Kolkata",
        "manager_email":"mgr.netops@nexusdesk.com",
    },
    {
        "key":          "cloud",
        "name":         "Cloud Platform",
        "description":  "Manages cloud infrastructure across AWS, Azure and GCP",
        "domain_focus": ["cloud", "infrastructure"],
        "region":       "Asia Pacific",
        "timezone":     "Asia/Singapore",
        "manager_email":"mgr.cloud@nexusdesk.com",
    },
    {
        "key":          "dba",
        "name":         "Database Administration",
        "description":  "Manages all relational and NoSQL database systems",
        "domain_focus": ["database"],
        "region":       "India",
        "timezone":     "Asia/Kolkata",
        "manager_email":"mgr.dba@nexusdesk.com",
    },
    {
        "key":          "devops",
        "name":         "DevOps Engineering",
        "description":  "Manages CI/CD pipelines, Kubernetes, and software delivery",
        "domain_focus": ["devops", "software"],
        "region":       "Europe",
        "timezone":     "Europe/Berlin",
        "manager_email":"mgr.devops@nexusdesk.com",
    },
    {
        "key":          "hardware",
        "name":         "Hardware & Endpoint",
        "description":  "Manages physical servers, workstations and endpoint devices",
        "domain_focus": ["hardware", "endpoint_management"],
        "region":       "Middle East",
        "timezone":     "Asia/Dubai",
        "manager_email":"mgr.hardware@nexusdesk.com",
    },
    {
        "key":          "security",
        "name":         "Cybersecurity Operations",
        "description":  "Manages firewalls, SIEM, WAF, IDS/IPS and security tooling",
        "domain_focus": ["security"],
        "region":       "Europe",
        "timezone":     "Europe/London",
        "manager_email":"mgr.security@nexusdesk.com",
    },
    {
        "key":          "erp",
        "name":         "ERP & Collaboration",
        "description":  "Manages SAP, Oracle EBS, ServiceNow, Exchange and communication platforms",
        "domain_focus": ["erp_business_apps", "email_communication"],
        "region":       "Asia Pacific",
        "timezone":     "Asia/Shanghai",
        "manager_email":"mgr.erp@nexusdesk.com",
    },
]

ENGINEERS = [
    # ── Network Operations ────────────────────────────────────────────────────
    {
        "name":     "Aryan Kapoor",
        "email":    "eng.netops1@nexusdesk.com",
        "domains":  ["networking", "identity_access"],
        "city":     "Mumbai",
        "country":  "India",
        "timezone": "Asia/Kolkata",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "netops",
    },
    {
        "name":     "Zara Ahmed",
        "email":    "eng.netops2@nexusdesk.com",
        "domains":  ["networking"],
        "city":     "Mumbai",
        "country":  "India",
        "timezone": "Asia/Kolkata",
        "seniority": SeniorityLevel.MID,
        "team":     "netops",
    },
    {
        "name":     "Carlos Mendez",
        "email":    "eng.netops3@nexusdesk.com",
        "domains":  ["networking", "identity_access"],
        "city":     "Mexico City",
        "country":  "Mexico",
        "timezone": "America/Mexico_City",
        "seniority": SeniorityLevel.MID,
        "team":     "netops",
    },

    # ── Cloud Platform ────────────────────────────────────────────────────────
    {
        "name":     "Lena Hoffman",
        "email":    "eng.cloud1@nexusdesk.com",
        "domains":  ["cloud", "infrastructure"],
        "city":     "Singapore",
        "country":  "Singapore",
        "timezone": "Asia/Singapore",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "cloud",
    },
    {
        "name":     "Kevin Osei",
        "email":    "eng.cloud2@nexusdesk.com",
        "domains":  ["cloud"],
        "city":     "Nairobi",
        "country":  "Kenya",
        "timezone": "Africa/Nairobi",
        "seniority": SeniorityLevel.MID,
        "team":     "cloud",
    },
    {
        "name":     "Haruto Yamamoto",
        "email":    "eng.cloud3@nexusdesk.com",
        "domains":  ["cloud", "infrastructure"],
        "city":     "Tokyo",
        "country":  "Japan",
        "timezone": "Asia/Tokyo",
        "seniority": SeniorityLevel.MID,
        "team":     "cloud",
    },

    # ── Database Administration ───────────────────────────────────────────────
    {
        "name":     "Divya Krishnamurthy",
        "email":    "eng.dba1@nexusdesk.com",
        "domains":  ["database"],
        "city":     "Hyderabad",
        "country":  "India",
        "timezone": "Asia/Kolkata",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "dba",
    },
    {
        "name":     "Felix Wagner",
        "email":    "eng.dba2@nexusdesk.com",
        "domains":  ["database"],
        "city":     "Frankfurt",
        "country":  "Germany",
        "timezone": "Europe/Berlin",
        "seniority": SeniorityLevel.MID,
        "team":     "dba",
    },
    {
        "name":     "Amara Diallo",
        "email":    "eng.dba3@nexusdesk.com",
        "domains":  ["database"],
        "city":     "Dakar",
        "country":  "Senegal",
        "timezone": "Africa/Dakar",
        "seniority": SeniorityLevel.MID,
        "team":     "dba",
    },

    # ── DevOps Engineering ────────────────────────────────────────────────────
    {
        "name":     "Stefan Kowalski",
        "email":    "eng.devops1@nexusdesk.com",
        "domains":  ["devops", "software"],
        "city":     "Warsaw",
        "country":  "Poland",
        "timezone": "Europe/Warsaw",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "devops",
    },
    {
        "name":     "Aiko Tanaka",
        "email":    "eng.devops2@nexusdesk.com",
        "domains":  ["devops"],
        "city":     "Osaka",
        "country":  "Japan",
        "timezone": "Asia/Tokyo",
        "seniority": SeniorityLevel.MID,
        "team":     "devops",
    },
    {
        "name":     "Lucas Fernandez",
        "email":    "eng.devops3@nexusdesk.com",
        "domains":  ["devops", "software"],
        "city":     "Buenos Aires",
        "country":  "Argentina",
        "timezone": "America/Argentina/Buenos_Aires",
        "seniority": SeniorityLevel.MID,
        "team":     "devops",
    },

    # ── Hardware & Endpoint ───────────────────────────────────────────────────
    {
        "name":     "Omar Al-Farsi",
        "email":    "eng.hw1@nexusdesk.com",
        "domains":  ["hardware", "endpoint_management"],
        "city":     "Dubai",
        "country":  "UAE",
        "timezone": "Asia/Dubai",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "hardware",
    },
    {
        "name":     "Preethi Subramaniam",
        "email":    "eng.hw2@nexusdesk.com",
        "domains":  ["hardware"],
        "city":     "Chennai",
        "country":  "India",
        "timezone": "Asia/Kolkata",
        "seniority": SeniorityLevel.MID,
        "team":     "hardware",
    },
    {
        "name":     "Nathan Brooks",
        "email":    "eng.hw3@nexusdesk.com",
        "domains":  ["endpoint_management", "hardware"],
        "city":     "Toronto",
        "country":  "Canada",
        "timezone": "America/Toronto",
        "seniority": SeniorityLevel.MID,
        "team":     "hardware",
    },

    # ── Cybersecurity ─────────────────────────────────────────────────────────
    {
        "name":     "Isabella Rossi",
        "email":    "eng.sec1@nexusdesk.com",
        "domains":  ["security"],
        "city":     "Milan",
        "country":  "Italy",
        "timezone": "Europe/Rome",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "security",
    },
    {
        "name":     "Kwame Asante",
        "email":    "eng.sec2@nexusdesk.com",
        "domains":  ["security"],
        "city":     "Accra",
        "country":  "Ghana",
        "timezone": "Africa/Accra",
        "seniority": SeniorityLevel.MID,
        "team":     "security",
    },
    {
        "name":     "Sven Lindqvist",
        "email":    "eng.sec3@nexusdesk.com",
        "domains":  ["security"],
        "city":     "Stockholm",
        "country":  "Sweden",
        "timezone": "Europe/Stockholm",
        "seniority": SeniorityLevel.MID,
        "team":     "security",
    },

    # ── ERP & Collaboration ───────────────────────────────────────────────────
    {
        "name":     "Wei Zhang",
        "email":    "eng.erp1@nexusdesk.com",
        "domains":  ["erp_business_apps", "email_communication"],
        "city":     "Shanghai",
        "country":  "China",
        "timezone": "Asia/Shanghai",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "erp",
    },
    {
        "name":     "Chioma Eze",
        "email":    "eng.erp2@nexusdesk.com",
        "domains":  ["erp_business_apps"],
        "city":     "Lagos",
        "country":  "Nigeria",
        "timezone": "Africa/Lagos",
        "seniority": SeniorityLevel.MID,
        "team":     "erp",
    },
    {
        "name":     "Rafael Souza",
        "email":    "eng.erp3@nexusdesk.com",
        "domains":  ["email_communication", "erp_business_apps"],
        "city":     "Sao Paulo",
        "country":  "Brazil",
        "timezone": "America/Sao_Paulo",
        "seniority": SeniorityLevel.MID,
        "team":     "erp",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Managers
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─"*60)
print("STEP 1 — Creating managers")
print("─"*60)

manager_users = {}

for m in MANAGERS:
    existing = db.query(User).filter(User.email == m["email"]).first()
    if existing:
        print(f"  ⚠ SKIP   {m['name']:30s} ({m['email']})")
        manager_users[m["team_key"]] = existing
        if str(existing.role) != "manager":
            existing.role     = UserRole.MANAGER
            existing.is_verified = True
            db.commit()
        continue

    user = User(
        id              = uuid.uuid4(),
        email           = m["email"],
        full_name       = m["name"],
        hashed_password = PASSWORD,
        role            = UserRole.MANAGER,
        is_active       = True,
        is_verified     = True,
        city            = m["city"],
        country         = m["country"],
        timezone        = m["timezone"],
        created_at      = datetime.utcnow(),
        updated_at      = datetime.utcnow(),
    )
    db.add(user)
    db.flush()
    manager_users[m["team_key"]] = user
    print(f"  ✓ CREATE {m['name']:30s} ({m['email']})")

db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Teams
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─"*60)
print("STEP 2 — Creating teams")
print("─"*60)

team_objects = {}

for t in TEAMS:
    existing = db.query(Team).filter(Team.name == t["name"]).first()
    if existing:
        print(f"  ⚠ SKIP   {t['name']} ({existing.team_id})")
        team_objects[t["key"]] = existing
        continue

    mgr = manager_users.get(t["key"])
    if not mgr:
        print(f"  ✗ ERROR  {t['name']} — manager not found")
        continue

    team = Team(
        id                  = uuid.uuid4(),
        team_id             = gen_team_id(),
        name                = t["name"],
        description         = t["description"],
        domain_focus        = t["domain_focus"],
        region              = t["region"],
        timezone            = t["timezone"],
        manager_id          = mgr.id,
        is_active           = True,
        max_ticket_capacity = 30,
        active_ticket_count = 0,
        total_resolved      = 0,
        avg_resolution_time = 0,
        sla_compliance_rate = 100,
        created_at          = datetime.utcnow(),
        updated_at          = datetime.utcnow(),
    )
    db.add(team)
    db.flush()
    team_objects[t["key"]] = team
    print(f"  ✓ CREATE {t['name']:35s} ({team.team_id}) | {', '.join(t['domain_focus'])}")

db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Engineers
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─"*60)
print("STEP 3 — Creating engineers")
print("─"*60)

created = 0
skipped = 0

for eng in ENGINEERS:
    existing_user = db.query(User).filter(User.email == eng["email"]).first()

    if existing_user:
        existing_eng = db.query(Engineer).filter(Engineer.user_id == existing_user.id).first()
        team_obj     = team_objects.get(eng["team"])
        if existing_eng and team_obj:
            already = db.query(TeamMember).filter(
                TeamMember.team_id == team_obj.id,
                TeamMember.user_id == existing_user.id,
            ).first()
            if not already:
                db.add(TeamMember(
                    id           = uuid.uuid4(),
                    team_id      = team_obj.id,
                    user_id      = existing_user.id,
                    role_in_team = TeamMemberRole.MEMBER,
                    joined_at    = datetime.utcnow(),
                ))
                db.commit()
        print(f"  ⚠ SKIP   {eng['name']:30s} ({eng['email']})")
        skipped += 1
        continue

    user = User(
        id              = uuid.uuid4(),
        email           = eng["email"],
        full_name       = eng["name"],
        hashed_password = PASSWORD,
        role            = UserRole.ENGINEER,
        is_active       = True,
        is_verified     = True,
        city            = eng["city"],
        country         = eng["country"],
        timezone        = eng["timezone"],
        created_at      = datetime.utcnow(),
        updated_at      = datetime.utcnow(),
    )
    db.add(user)
    db.flush()

    engineer = Engineer(
        id                  = uuid.uuid4(),
        user_id             = user.id,
        engineer_id         = gen_engineer_id(),
        domain_expertise    = eng["domains"],
        region              = eng["city"],
        timezone            = eng["timezone"],
        seniority_level     = eng.get("seniority", SeniorityLevel.MID),
        max_ticket_capacity = 10,
        availability_status = AvailabilityStatus.AVAILABLE,
        active_ticket_count = 0,
        is_activated        = True,
        temp_password_hash  = None,
        total_resolved      = 0,
        avg_resolution_time = 60,
        sla_compliance_rate = 100,
        created_at          = datetime.utcnow(),
        updated_at          = datetime.utcnow(),
    )
    db.add(engineer)
    db.flush()

    team_obj = team_objects.get(eng["team"])
    if team_obj:
        db.add(TeamMember(
            id           = uuid.uuid4(),
            team_id      = team_obj.id,
            user_id      = user.id,
            role_in_team = TeamMemberRole.MEMBER,
            joined_at    = datetime.utcnow(),
        ))

    db.commit()
    created += 1
    tid = team_obj.team_id if team_obj else "NO TEAM"
    print(f"  ✓ CREATE {eng['name']:30s} | {eng['email']:35s} | {tid}")

db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "═"*60)
print("SEED COMPLETE")
print("═"*60)
print(f"  Managers : {len(MANAGERS)}")
print(f"  Teams    : {len(team_objects)}")
print(f"  Engineers: created={created} skipped={skipped}")
print(f"\n  Password for all: {PLAIN_PASSWORD}")
print("\n  Routing map:")
for t in TEAMS:
    key     = t["key"]
    team_obj = team_objects.get(key)
    tid     = team_obj.team_id if team_obj else "?"
    engs    = [e for e in ENGINEERS if e["team"] == key]
    print(f"  {t['name']:35s} ({tid})")
    print(f"    Manager : mgr.{key}@nexusdesk.com")
    for e in engs:
        print(f"    Engineer: {e['email']}")
print("═"*60)

db.close()