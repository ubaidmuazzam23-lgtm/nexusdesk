<div align="center">

```
███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗██████╗ ███████╗███████╗██╗  ██╗
████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝██╔══██╗██╔════╝██╔════╝██║ ██╔╝
██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗██║  ██║█████╗  ███████╗█████╔╝ 
██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║██║  ██║██╔══╝  ╚════██║██╔═██╗ 
██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║██████╔╝███████╗███████║██║  ██╗
╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝
```

**AI-Powered Enterprise IT Support Platform**



[![Next.js](https://img.shields.io/badge/Next.js-15-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4.5-D97706?style=flat-square)](https://anthropic.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-8B5CF6?style=flat-square)](https://trychroma.com)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=flat-square&logo=supabase)](https://supabase.com)

</div>

---

## What is NexusDesk?

NexusDesk is a full-stack AI IT support platform that replaces traditional helpdesk ticketing with an intelligent, self-improving system. Users describe their issue in natural language, the AI diagnoses and attempts resolution, and only escalates to a human engineer when necessary — routing to the best available engineer based on domain expertise, timezone proximity, and workload.

The system **learns from every resolved ticket**, automatically indexing engineer resolution notes into a RAG knowledge base so future users with similar issues get better answers immediately.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER (Browser)                          │
│  Chat Interface · Screenshot Upload · Ticket Tracker            │
└─────────────────────────┬───────────────────────────────────────┘
                          │ REST API
┌─────────────────────────▼───────────────────────────────────────┐
│                    FastAPI Backend                               │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐   │
│  │  Claude AI   │  │  RAG Pipeline│  │   Routing Engine    │   │
│  │  Sonnet 4.5  │  │  ChromaDB +  │  │  Domain + Timezone  │   │
│  │  Chat + Class│  │  MiniLM-L6   │  │  + Workload Score   │   │
│  └──────────────┘  └──────────────┘  └─────────────────────┘   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐   │
│  │  CNN (ResNet)│  │  BiLSTM      │  │   Gmail SMTP        │   │
│  │  Screenshot  │  │  Complexity  │  │   Email Notifs      │   │
│  │  Classifier  │  │  Detection   │  │                     │   │
│  └──────────────┘  └──────────────┘  └─────────────────────┘   │
│                                                                 │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                    Supabase (PostgreSQL)                         │
│  Users · Engineers · Tickets · Sessions                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## AI Pipeline

### 1 · Claude Sonnet 4.5 — Conversational Diagnosis
The chat system uses Claude with a structured prompt to diagnose IT issues through conversation. On every user message:
- A lightweight **classification call** (max 120 tokens) detects domain and severity
- The **RAG context** is injected into the system prompt if relevant KB articles exist
- Claude responds with plain-language troubleshooting steps
- After 2 failed attempts, Claude recommends escalation

### 2 · RAG Knowledge Base (ChromaDB + sentence-transformers)
```
Admin/Engineer uploads PDF/TXT/MD
          ↓
Text extracted → chunked (400 words, 60 overlap)
          ↓
Embedded with all-MiniLM-L6-v2 (384-dim vectors)
          ↓
Stored in ChromaDB (cosine similarity index)
          ↓
On every user message → top-K search → inject into Claude prompt
```
**Auto-indexing:** When an engineer resolves a ticket with notes, the resolution is automatically indexed as a new KB article. The system learns from every resolved ticket.

### 3 · CNN Screenshot Classifier (ResNet50)
- Fine-tuned on 25 error classes (BSOD, SSL errors, app crashes, DNS failures, etc.)
- 92.1% accuracy on combined dataset
- Confidence ≥ 85% → CNN result injected into Claude context
- Error class mapped to domain and severity automatically

### 4 · BiLSTM Complexity Detector
- 2-layer BiLSTM trained on 2,700 synthetic IT support tickets
- Classifies ticket complexity: Simple / Moderate / Complex
- 65.2% accuracy — used for seniority-based engineer routing

### 5 · Routing Engine
```python
score = 0
if domain_match:      score += 10
if tz_diff == 0:      score += 5
elif tz_diff <= 3h:   score += 3
elif tz_diff <= 6h:   score += 1
score -= active_ticket_count  # workload penalty
```
Best available engineer assigned automatically on ticket creation.

---

## ML Model Stats

| Model | Task | Accuracy | Classes | Parameters |
|-------|------|----------|---------|------------|
| ResNet50 (CNN) | Screenshot error classification | 92.1% | 25 | 24.7M |
| BiLSTM | Ticket complexity detection | 65.2% | 3 | 2.06M |
| all-MiniLM-L6-v2 | Semantic embedding (RAG) | — | — | 22.7M |

---

## Features

### User Portal
- **AI Chat** — Describe issue in natural language, Claude diagnoses and guides resolution
- **Screenshot Upload** — Attach error screenshots, CNN detects error type instantly
- **Intent Selection** — Solve a problem or submit a service request
- **Ticket Tracker** — View all raised tickets with engineer assignment and live timezone

### Engineer Dashboard
- **Ticket Queue** — Table view with priority, domain, user location, live user clock
- **Ticket Detail** — AI diagnosis, CNN detection, steps tried, screenshot viewer
- **Knowledge Base Similarity** — Cosine similarity scores for relevant KB articles per ticket
- **Resolution Notes** — Auto-indexed to KB on resolve
- **Knowledge Base Search** — Semantic search across all IT documentation
- **History Tab** — Full resolution history with SLA stats

### Admin Panel
- **Overview** — Live Leaflet map of engineer locations, KPI cards, routing modal, activity stream
- **Engineers** — Full CRUD with domain expertise, workload bars, activation management
- **Tickets** — Global view with priority/status filters, detail panel with AI diagnosis
- **Knowledge Base** — Document management, auto-indexed vs manual badges, inline search test
- **Analytics** — Ticket volume charts, domain breakdown, priority distribution

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, TypeScript, inline styles |
| Backend | FastAPI, Python 3.9, SQLAlchemy |
| Database | Supabase (PostgreSQL) |
| AI | Anthropic Claude Sonnet 4.5 |
| ML | TensorFlow/Keras (CNN + BiLSTM) |
| RAG | ChromaDB, sentence-transformers |
| Auth | JWT (access + refresh tokens) |
| Email | Gmail SMTP |
| Maps | Leaflet.js |
| Fonts | Inter, JetBrains Mono, Cormorant Garamond |

---

## Project Structure

```
ai-it-support/
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── engineer.py
│   │   │   ├── admin.py
│   │   │   ├── analytics.py
│   │   │   └── knowledge.py
│   │   ├── services/
│   │   │   ├── chat_service.py       ← Claude + RAG + CNN
│   │   │   ├── engineer_service.py   ← resolve + auto-index
│   │   │   ├── knowledge_service.py  ← ChromaDB RAG pipeline
│   │   │   └── admin_service.py
│   │   ├── ml/
│   │   │   ├── cnn/                  ← ResNet50 screenshot classifier
│   │   │   └── bilstm/               ← complexity detector
│   │   ├── models/                   ← SQLAlchemy models
│   │   └── schemas/                  ← Pydantic schemas
│   └── uploads/screenshots/          ← user screenshot storage
│
└── frontend/
    └── src/app/
        ├── auth/                     ← login, register, forgot password
        ├── chat/                     ← user chat interface
        ├── engineer/
        │   ├── dashboard/            ← ticket queue + detail panel
        │   └── knowledge/            ← KB search + upload
        └── admin/
            ├── overview/             ← map + KPIs + routing modal
            ├── engineers/            ← engineer management
            ├── tickets/              ← global ticket view
            └── knowledge/            ← KB management
```

---

## Setup

### Prerequisites
```
Python 3.9+
Node.js 18+
PostgreSQL (via Supabase)
```

### Backend
```bash
cd backend
python -m venv itsupport-env
source itsupport-env/bin/activate

pip install -r requirements.txt
pip install chromadb sentence-transformers pypdf2

cp .env.example .env
# Fill in: DATABASE_URL, ANTHROPIC_API_KEY, JWT_SECRET, GMAIL credentials

uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install

cp .env.example .env.local
# Set: NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev
```

### Environment Variables

**Backend `.env`**
```
DATABASE_URL=postgresql://...
ANTHROPIC_API_KEY=sk-ant-...
JWT_SECRET=your-secret-key
JWT_REFRESH_SECRET=your-refresh-secret
GMAIL_USER=your@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
FRONTEND_URL=http://localhost:3000
```

**Frontend `.env.local`**
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Demo Flow

```
1. User logs in → Chat page
2. Types: "my SSL certificate is showing ERR_CERT_EXPIRED"
   → Claude classifies: domain=security, severity=high
   → RAG searches KB: finds relevant SSL guide (68% match)
   → Claude responds with specific certbot/nginx steps

3. After 2-3 attempts → "Raise Support Ticket" button appears
4. User fills form → ticket created → best engineer auto-assigned
   (domain match + timezone proximity + workload score)

5. Engineer logs in → sees ticket in queue
   → AI diagnosis pre-filled
   → KB Similarity panel shows matching articles with cosine %
   → Types resolution notes → clicks "Mark Resolved"
   → Notes auto-indexed to KB (🧠 KB Auto-indexed: T-1001)

6. Next user with similar SSL issue:
   → RAG finds resolved ticket (72% match)
   → Claude gives specific nginx/certbot steps immediately
```

---

## API Endpoints

```
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/chat/message
POST   /api/v1/chat/upload-screenshot
POST   /api/v1/chat/escalate
GET    /api/v1/chat/tickets

PATCH  /api/v1/engineer/tickets/{id}/resolve
GET    /api/v1/engineer/tickets
GET    /api/v1/engineer/stats

POST   /api/v1/knowledge/upload
POST   /api/v1/knowledge/search
GET    /api/v1/knowledge/documents
GET    /api/v1/knowledge/ticket-similarity/{ticket_id}

GET    /api/v1/analytics/overview
GET    /api/v1/analytics/by-domain
GET    /api/v1/analytics/over-time

GET    /api/v1/admin/engineers
POST   /api/v1/admin/engineers
GET    /api/v1/admin/tickets
```

---

## Team



---

<div align="center">

*Built with Claude Sonnet 4.5 · ChromaDB · ResNet50 · FastAPI · Next.js*

</div># nexusdesk
