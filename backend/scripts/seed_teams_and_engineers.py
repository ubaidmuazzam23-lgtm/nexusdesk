# backend/seed_teams_and_engineers.py
#
# PURPOSE:
#   Seeds 4 teams + 4 managers + engineers whose emails EXACTLY match
#   the contact/manager emails in the original PDF CSV:
#
#   Teams:    team1, team2, team3, team4
#   Managers: devmgr1@abc.com ... devmgr4@abc.com  (match ENGINEERING_DEV_MANAGER_EMAIL)
#   Engineers: teama@xyz.com ... teamd@xyz.com      (match C_CONTACT in CSV)
#
#   When a ticket is raised for instance1 (contact: teama@xyz.com,
#   manager: devmgr1@abc.com), the routing engine will:
#     1. Find teama@xyz.com as a registered engineer → route directly
#     2. OR find devmgr1@abc.com managing a team → route to that team
#
# RUN:
#   cd backend
#   python seed_teams_and_engineers.py
#
# NOTES:
#   - Uses is_activated=True to bypass email activation flow (seed only)
#   - engineer_id format matches _generate_engineer_id() → ENG-XXXX
#   - All passwords: Nexus@1234

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

import uuid
import secrets
from datetime import datetime

from app.core.database import SessionLocal
from app.models.user import User, UserRole
from app.models.engineer import Engineer, AvailabilityStatus, SeniorityLevel
from app.models.team import Team, TeamMember, TeamMemberRole
from app.core.security import hash_password

db = SessionLocal()

PASSWORD      = hash_password("Nexus@1234")
PLAIN_PASSWORD = "Nexus@1234"

# ─────────────────────────────────────────────────────────────────────────────
# HELPER — generate ENG-XXXX style ID (matches admin_service logic)
# ─────────────────────────────────────────────────────────────────────────────

def gen_engineer_id() -> str:
    while True:
        eid = f"ENG-{secrets.randbelow(9000) + 1000}"
        existing = db.query(Engineer).filter(Engineer.engineer_id == eid).first()
        if not existing:
            return eid


def gen_team_id() -> str:
    while True:
        tid = f"TM-{secrets.randbelow(9000) + 1000}"
        existing = db.query(Team).filter(Team.team_id == tid).first()
        if not existing:
            return tid


# ─────────────────────────────────────────────────────────────────────────────
# DATA — matches original PDF CSV structure exactly
# ─────────────────────────────────────────────────────────────────────────────

# 4 managers — emails match ENGINEERING_DEV_MANAGER_EMAIL in CSV
MANAGERS = [
    {
        "name":     "Dev Manager 1",
        "email":    "devmgr1@abc.com",
        "timezone": "Asia/Kolkata",
        "city":     "Mumbai",
        "country":  "India",
    },
    {
        "name":     "Dev Manager 2",
        "email":    "devmgr2@abc.com",
        "timezone": "America/New_York",
        "city":     "New York",
        "country":  "United States",
    },
    {
        "name":     "Dev Manager 3",
        "email":    "devmgr3@abc.com",
        "timezone": "Europe/London",
        "city":     "London",
        "country":  "United Kingdom",
    },
    {
        "name":     "Dev Manager 4",
        "email":    "devmgr4@abc.com",
        "timezone": "Asia/Singapore",
        "city":     "Singapore",
        "country":  "Singapore",
    },
]

# 4 teams — one per manager, domain_focus matches the verticals in the CSV
TEAMS = [
    {
        "name":         "team1",
        "description":  "Networking, Identity & Access, Cloud Infrastructure",
        "domain_focus": ["networking", "identity_access", "cloud"],
        "region":       "India",
        "timezone":     "Asia/Kolkata",
        "manager_email": "devmgr1@abc.com",
    },
    {
        "name":         "team2",
        "description":  "Database, DevOps, Software Engineering",
        "domain_focus": ["database", "devops", "software"],
        "region":       "US",
        "timezone":     "America/New_York",
        "manager_email": "devmgr2@abc.com",
    },
    {
        "name":         "team3",
        "description":  "Hardware, Infrastructure, Endpoint Management",
        "domain_focus": ["hardware", "infrastructure", "endpoint_management"],
        "region":       "Europe",
        "timezone":     "Europe/London",
        "manager_email": "devmgr3@abc.com",
    },
    {
        "name":         "team4",
        "description":  "Security, ERP & Business Apps, Email & Communication",
        "domain_focus": ["security", "erp_business_apps", "email_communication"],
        "region":       "Asia Pacific",
        "timezone":     "Asia/Singapore",
        "manager_email": "devmgr4@abc.com",
    },
]

# Engineers — C_CONTACT emails from CSV + extra engineers per team
# teama@xyz.com → team1, teamb@xyz.com → team2, etc.
ENGINEERS = [
    # ── team1 engineers ──────────────────────────────────────────────────────
    {
        "name":     "Team A Engineer",
        "email":    "teama@xyz.com",        # matches C_CONTACT for instance1, web-server-01, auth-server-01
        "domains":  ["networking", "identity_access", "cloud"],
        "region":   "India",
        "timezone": "Asia/Kolkata",
        "city":     "Mumbai",
        "country":  "India",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "team1",
    },
    {
        "name":     "Raj Sharma",
        "email":    "raj.sharma@nexusdesk.com",
        "domains":  ["networking", "cloud"],
        "region":   "India",
        "timezone": "Asia/Kolkata",
        "city":     "Mumbai",
        "country":  "India",
        "seniority": SeniorityLevel.MID,
        "team":     "team1",
    },
    {
        "name":     "Aisha Rahman",
        "email":    "aisha.rahman@nexusdesk.com",
        "domains":  ["identity_access", "networking"],
        "region":   "India",
        "timezone": "Asia/Dubai",
        "city":     "Dubai",
        "country":  "UAE",
        "seniority": SeniorityLevel.MID,
        "team":     "team1",
    },

    # ── team2 engineers ──────────────────────────────────────────────────────
    {
        "name":     "Team B Engineer",
        "email":    "teamb@xyz.com",        # matches C_CONTACT for instance2, db-server-01, ml-server-01
        "domains":  ["database", "devops", "software"],
        "region":   "US",
        "timezone": "America/New_York",
        "city":     "New York",
        "country":  "United States",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "team2",
    },
    {
        "name":     "Arjun Mehta",
        "email":    "arjun.mehta@nexusdesk.com",
        "domains":  ["database"],
        "region":   "India",
        "timezone": "Asia/Kolkata",
        "city":     "Hyderabad",
        "country":  "India",
        "seniority": SeniorityLevel.MID,
        "team":     "team2",
    },
    {
        "name":     "Ryan OConnor",
        "email":    "ryan.oconnor@nexusdesk.com",
        "domains":  ["devops", "software"],
        "region":   "US",
        "timezone": "America/New_York",
        "city":     "Boston",
        "country":  "United States",
        "seniority": SeniorityLevel.MID,
        "team":     "team2",
    },

    # ── team3 engineers ──────────────────────────────────────────────────────
    {
        "name":     "Team C Engineer",
        "email":    "teamc@xyz.com",        # matches C_CONTACT for instance3, api-server-01, monitor-server-01
        "domains":  ["hardware", "infrastructure", "endpoint_management"],
        "region":   "Europe",
        "timezone": "Europe/London",
        "city":     "London",
        "country":  "United Kingdom",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "team3",
    },
    {
        "name":     "James Patel",
        "email":    "james.patel@nexusdesk.com",
        "domains":  ["infrastructure", "hardware"],
        "region":   "Europe",
        "timezone": "Europe/London",
        "city":     "London",
        "country":  "United Kingdom",
        "seniority": SeniorityLevel.MID,
        "team":     "team3",
    },
    {
        "name":     "Nina Petrov",
        "email":    "nina.petrov@nexusdesk.com",
        "domains":  ["endpoint_management", "infrastructure"],
        "region":   "Europe",
        "timezone": "Europe/Berlin",
        "city":     "Berlin",
        "country":  "Germany",
        "seniority": SeniorityLevel.MID,
        "team":     "team3",
    },

    # ── team4 engineers ──────────────────────────────────────────────────────
    {
        "name":     "Team D Engineer",
        "email":    "teamd@xyz.com",        # matches C_CONTACT for instance4, cache-server-01, search-server-01
        "domains":  ["security", "erp_business_apps", "email_communication"],
        "region":   "Asia Pacific",
        "timezone": "Asia/Singapore",
        "city":     "Singapore",
        "country":  "Singapore",
        "seniority": SeniorityLevel.SENIOR,
        "team":     "team4",
    },
    {
        "name":     "Yuki Tanaka",
        "email":    "yuki.tanaka@nexusdesk.com",
        "domains":  ["security", "email_communication"],
        "region":   "Asia Pacific",
        "timezone": "Asia/Tokyo",
        "city":     "Tokyo",
        "country":  "Japan",
        "seniority": SeniorityLevel.MID,
        "team":     "team4",
    },
    {
        "name":     "Emma Wilson",
        "email":    "emma.wilson@nexusdesk.com",
        "domains":  ["erp_business_apps", "security"],
        "region":   "US",
        "timezone": "America/Chicago",
        "city":     "Chicago",
        "country":  "United States",
        "seniority": SeniorityLevel.MID,
        "team":     "team4",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Create managers
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─"*60)
print("STEP 1 — Creating managers")
print("─"*60)

manager_users = {}  # email → User object

for m in MANAGERS:
    existing = db.query(User).filter(User.email == m["email"]).first()
    if existing:
        print(f"  ⚠ SKIP   {m['name']:25s} ({m['email']}) — already exists")
        manager_users[m["email"]] = existing
        # Ensure role is manager and is_verified
        if str(existing.role) != "manager":
            existing.role = UserRole.MANAGER
            existing.is_verified = True
            db.commit()
        continue

    user = User(
        id               = uuid.uuid4(),
        email            = m["email"],
        full_name        = m["name"],
        hashed_password  = PASSWORD,
        role             = UserRole.MANAGER,
        is_active        = True,
        is_verified      = True,   # skip activation for seed
        city             = m["city"],
        country          = m["country"],
        timezone         = m["timezone"],
        created_at       = datetime.utcnow(),
        updated_at       = datetime.utcnow(),
    )
    db.add(user)
    db.flush()
    manager_users[m["email"]] = user
    print(f"  ✓ CREATE {m['name']:25s} ({m['email']})")

db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Create teams
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─"*60)
print("STEP 2 — Creating teams")
print("─"*60)

team_objects = {}  # team name → Team object

for t in TEAMS:
    existing = db.query(Team).filter(Team.name == t["name"]).first()
    if existing:
        print(f"  ⚠ SKIP   {t['name']} — already exists ({existing.team_id})")
        team_objects[t["name"]] = existing
        continue

    mgr_user = manager_users.get(t["manager_email"])
    if not mgr_user:
        print(f"  ✗ ERROR  {t['name']} — manager {t['manager_email']} not found, skipping")
        continue

    team = Team(
        id                  = uuid.uuid4(),
        team_id             = gen_team_id(),
        name                = t["name"],
        description         = t["description"],
        domain_focus        = t["domain_focus"],
        region              = t["region"],
        timezone            = t["timezone"],
        manager_id          = mgr_user.id,
        is_active           = True,
        max_ticket_capacity = 20,
        active_ticket_count = 0,
        total_resolved      = 0,
        avg_resolution_time = 0,
        sla_compliance_rate = 100,
        created_at          = datetime.utcnow(),
        updated_at          = datetime.utcnow(),
    )
    db.add(team)
    db.flush()
    team_objects[t["name"]] = team
    print(f"  ✓ CREATE {t['name']:10s} ({team.team_id}) | Manager: {t['manager_email']} | Domains: {', '.join(t['domain_focus'])}")

db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Create engineers + add to teams
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─"*60)
print("STEP 3 — Creating engineers")
print("─"*60)

created = 0
skipped = 0

for eng in ENGINEERS:
    existing_user = db.query(User).filter(User.email == eng["email"]).first()

    if existing_user:
        # Engineer already exists — just make sure they are in the right team
        existing_eng = db.query(Engineer).filter(Engineer.user_id == existing_user.id).first()
        team_obj = team_objects.get(eng["team"])

        if existing_eng and team_obj:
            already_member = db.query(TeamMember).filter(
                TeamMember.team_id == team_obj.id,
                TeamMember.user_id == existing_user.id,
            ).first()
            if not already_member:
                db.add(TeamMember(
                    id          = uuid.uuid4(),
                    team_id     = team_obj.id,
                    user_id     = existing_user.id,
                    role_in_team = TeamMemberRole.MEMBER,
                    joined_at   = datetime.utcnow(),
                ))
                db.commit()
                print(f"  ⚠ SKIP   {eng['name']:25s} ({eng['email']}) — already exists, added to {eng['team']}")
            else:
                print(f"  ⚠ SKIP   {eng['name']:25s} ({eng['email']}) — already exists + already in {eng['team']}")
        else:
            print(f"  ⚠ SKIP   {eng['name']:25s} ({eng['email']}) — already exists")

        skipped += 1
        continue

    # Create user
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

    # Create engineer profile
    engineer = Engineer(
        id                  = uuid.uuid4(),
        user_id             = user.id,
        engineer_id         = gen_engineer_id(),
        domain_expertise    = eng["domains"],
        region              = eng["region"],
        timezone            = eng["timezone"],
        seniority_level     = eng.get("seniority", SeniorityLevel.MID),
        max_ticket_capacity = 10,
        availability_status = AvailabilityStatus.AVAILABLE,
        active_ticket_count = 0,
        is_activated        = True,   # bypass email activation for seed
        temp_password_hash  = None,
        total_resolved      = 0,
        avg_resolution_time = 60,
        sla_compliance_rate = 100,
        created_at          = datetime.utcnow(),
        updated_at          = datetime.utcnow(),
    )
    db.add(engineer)
    db.flush()

    # Add to team
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

    team_id_str = team_obj.team_id if team_obj else "NO TEAM"
    print(f"  ✓ CREATE {eng['name']:25s} | {eng['email']:35s} | {', '.join(eng['domains'])[:30]:30s} | {team_id_str}")

db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Summary
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "═"*60)
print("SEED COMPLETE")
print("═"*60)
print(f"  Managers : {len(MANAGERS)}")
print(f"  Teams    : {len(team_objects)}")
print(f"  Engineers: created={created} skipped={skipped}")
print(f"\n  Password for all accounts: {PLAIN_PASSWORD}")
print(f"\n  Routing match check:")
print(f"  instance1 / web-server-01  → teama@xyz.com  → team1 (devmgr1@abc.com)")
print(f"  instance2 / db-server-01   → teamb@xyz.com  → team2 (devmgr2@abc.com)")
print(f"  instance3 / api-server-01  → teamc@xyz.com  → team3 (devmgr3@abc.com)")
print(f"  instance4 / cache-server-01→ teamd@xyz.com  → team4 (devmgr4@abc.com)")
print("═"*60)

db.close()