# 🧠 Email Intelligence Bot — Senior Developer Guide

> A complete architectural and technical walkthrough based on your PDR.  
> This guide covers structure, technology choices, feature decisions, and the path to a working system.

---

## 📌 Table of Contents

1. [Project Analysis & Reality Check](#1-project-analysis--reality-check)
2. [Recommended Folder Structure](#2-recommended-folder-structure)
3. [Technology Deep Dive](#3-technology-deep-dive)
4. [Feature & Function Breakdown](#4-feature--function-breakdown)
5. [The Gmail Integration Layer](#5-the-gmail-integration-layer)
6. [The AI Classification Engine](#6-the-ai-classification-engine)
7. [The Policy & Safety Layer](#7-the-policy--safety-layer)
8. [The Feedback & Learning Loop](#8-the-feedback--learning-loop)
9. [The Dashboard (Frontend)](#9-the-dashboard-frontend)
10. [Database Design in Practice](#10-database-design-in-practice)
11. [Automation & Scheduling](#11-automation--scheduling)
12. [Development Phases — Practical Order](#12-development-phases--practical-order)
13. [Key Decisions You Need to Make](#13-key-decisions-you-need-to-make)
14. [Common Pitfalls to Avoid](#14-common-pitfalls-to-avoid)

---

## 1. Project Analysis & Reality Check

### What Your PDR Gets Right

Your PDR is architecturally sound. The separation of concerns — ingestion → preprocessing → classification → policy → action → feedback — is the correct mental model. Most amateur projects skip the **policy layer** and the **feedback loop**, which causes silent failures. You've included both, which is the mark of someone thinking like a systems designer, not just a coder.

### What Needs Sharpening

| PDR Assumption | Senior Dev Reality |
|---|---|
| "Run every 5–10 minutes" | Gmail Push Notifications (Pub/Sub) are far better than polling for real-time use |
| "LLM classification" as primary | LLMs are slow and expensive at scale; rules should catch 60–70% of emails first |
| "LangGraph" for orchestration | LangGraph is powerful but heavy for v1; start with plain Python pipelines, migrate later |
| "PostgreSQL from day one" | For personal use, SQLite is perfectly sufficient through Phase 3; migrate when needed |
| "Next.js Dashboard" | Streamlit or a simple React app is faster to build for a personal tool |
| "99% uptime" | You're building for yourself — this is over-engineered for v1; focus on correctness first |

### The Real Engineering Challenge

Your PDR correctly identifies it: **trust calibration over time**. The question isn't "can the LLM classify emails?" — it can. The question is "how do you know when to trust it enough to act automatically?" That answer comes from your feedback loop, which means the feedback system is the most important feature you'll build — not the classifier.

---

## 2. Recommended Folder Structure

This structure follows a **monorepo** pattern — everything lives in one repository, organized by responsibility.

```
email-intelligence-bot/
│
├── 📁 backend/                         # All Python server-side code
│   │
│   ├── 📁 api/                         # FastAPI application (HTTP layer)
│   │   ├── 📁 routes/                  # One file per feature area
│   │   │   ├── emails.py               # Email CRUD endpoints
│   │   │   ├── feedback.py             # Feedback submission endpoints
│   │   │   ├── rules.py                # Rules management endpoints
│   │   │   ├── analytics.py            # Dashboard metrics endpoints
│   │   │   └── auth.py                 # OAuth callback handler
│   │   ├── 📁 middleware/
│   │   │   ├── auth_middleware.py      # Token validation
│   │   │   └── error_handler.py        # Global error handling
│   │   ├── dependencies.py             # Shared FastAPI dependencies (DB session, etc.)
│   │   └── main.py                     # FastAPI app entrypoint
│   │
│   ├── 📁 core/                        # Business logic — framework-agnostic
│   │   ├── 📁 ingestion/
│   │   │   ├── gmail_client.py         # Gmail API wrapper
│   │   │   ├── sync_manager.py         # Incremental sync logic (tracks last fetched)
│   │   │   └── attachment_parser.py    # Metadata extraction from attachments
│   │   │
│   │   ├── 📁 preprocessing/
│   │   │   ├── html_cleaner.py         # Strip HTML, decode MIME
│   │   │   ├── text_normalizer.py      # Lowercase, remove noise
│   │   │   ├── feature_extractor.py    # Keywords, sender domain, has_attachment flags
│   │   │   └── summarizer.py           # Optional LLM summarization for long emails
│   │   │
│   │   ├── 📁 classification/
│   │   │   ├── rule_engine.py          # Deterministic rules (sender lists, keywords)
│   │   │   ├── llm_classifier.py       # LLM prompt + response parser
│   │   │   ├── confidence_filter.py    # Confidence threshold logic
│   │   │   └── classifier_pipeline.py  # Orchestrates rule → LLM → confidence check
│   │   │
│   │   ├── 📁 policy/
│   │   │   ├── safety_checks.py        # Hard rules: no delete if attachment, etc.
│   │   │   ├── policy_engine.py        # Applies all policies before action
│   │   │   └── override_manager.py     # Manual override handling
│   │   │
│   │   ├── 📁 actions/
│   │   │   ├── gmail_actions.py        # Label, archive, move, star via Gmail API
│   │   │   ├── action_logger.py        # Logs every action taken (for undo)
│   │   │   └── undo_manager.py         # Reverses actions by reading action log
│   │   │
│   │   └── 📁 feedback/
│   │       ├── feedback_processor.py   # Saves user corrections
│   │       ├── pattern_analyzer.py     # Offline analysis of feedback data
│   │       └── rule_suggester.py       # Suggests new rules from patterns
│   │
│   ├── 📁 workers/                     # Background task runners
│   │   ├── celery_app.py               # Celery configuration
│   │   ├── email_sync_task.py          # Scheduled email fetch task
│   │   ├── classification_task.py      # Async classification worker
│   │   └── analytics_task.py           # Periodic metrics computation
│   │
│   ├── 📁 db/                          # Database layer
│   │   ├── 📁 models/                  # SQLAlchemy ORM models
│   │   │   ├── email.py
│   │   │   ├── feedback.py
│   │   │   ├── rule.py
│   │   │   ├── action_log.py
│   │   │   └── user_preference.py
│   │   ├── 📁 migrations/              # Alembic migration files
│   │   ├── session.py                  # DB connection + session factory
│   │   └── repository/                 # Data access layer (query logic lives here)
│   │       ├── email_repo.py
│   │       ├── feedback_repo.py
│   │       └── rules_repo.py
│   │
│   ├── 📁 config/
│   │   ├── settings.py                 # Pydantic settings (reads from .env)
│   │   └── constants.py                # Category names, threshold values, etc.
│   │
│   ├── 📁 monitoring/
│   │   ├── metrics.py                  # Custom metric collectors
│   │   ├── drift_detector.py           # Detects distribution shift in categories
│   │   └── alerting.py                 # Sends alerts (email/log) on anomalies
│   │
│   └── 📁 tests/
│       ├── 📁 unit/
│       │   ├── test_rule_engine.py
│       │   ├── test_classifier.py
│       │   └── test_policy.py
│       ├── 📁 integration/
│       │   ├── test_gmail_client.py
│       │   └── test_pipeline.py
│       └── 📁 fixtures/
│           └── sample_emails/          # Mock email JSONs for testing
│
├── 📁 frontend/                        # Next.js / React dashboard
│   ├── 📁 app/                         # Next.js App Router
│   │   ├── 📁 dashboard/
│   │   │   ├── page.tsx                # Main review queue
│   │   │   ├── analytics/page.tsx      # Metrics charts
│   │   │   └── rules/page.tsx          # Rule management UI
│   │   └── layout.tsx
│   ├── 📁 components/
│   │   ├── EmailCard.tsx               # Single email review card
│   │   ├── CategoryBadge.tsx           # Color-coded category chip
│   │   ├── ConfidenceBar.tsx           # Visual confidence indicator
│   │   ├── FeedbackForm.tsx            # Approve / Edit UI
│   │   └── MetricsChart.tsx            # Recharts/Chart.js wrapper
│   ├── 📁 lib/
│   │   ├── api.ts                      # Backend API client (fetch wrappers)
│   │   └── types.ts                    # TypeScript interfaces mirroring backend models
│   └── 📁 hooks/
│       ├── useEmailQueue.ts            # Data fetching + pagination
│       └── useFeedback.ts              # Optimistic UI for feedback submission
│
├── 📁 scripts/                         # One-off utility scripts
│   ├── backfill_emails.py              # Classify historical emails in batch
│   ├── seed_rules.py                   # Load default rules into DB
│   └── export_feedback.py             # Export feedback data for analysis
│
├── 📁 docker/                          # Container configuration
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── docker-compose.yml             # Wires backend + frontend + DB + Redis together
│
├── 📁 docs/                            # Project documentation
│   ├── architecture.md
│   ├── api_reference.md
│   └── prompt_library.md              # Your LLM prompts, versioned
│
├── .env.example                        # Template for environment variables
├── .gitignore
├── README.md
└── Makefile                            # Shortcuts: make run, make test, make migrate
```

---

## 3. Technology Deep Dive

### 3.1 Python + FastAPI (Backend)

**What it is:** FastAPI is a modern Python web framework built on top of Starlette and Pydantic. It auto-generates OpenAPI documentation from your type hints.

**Why it fits here:**
- Native async support — critical for making Gmail API calls and LLM calls without blocking
- Pydantic models enforce data contracts at every layer (your email object, classification output, feedback schema)
- Built-in dependency injection makes swapping components (e.g., test DB vs. real DB) trivial

**Key features you'll use:**
- `@app.get`, `@app.post` — route decorators
- `BackgroundTasks` — fire-and-forget classification after email is received
- `Depends()` — inject DB sessions, auth tokens into routes automatically
- Pydantic `BaseModel` — define your email schema, classification output, feedback schema
- `HTTPException` — standardized error responses

**What to be careful about:**
- FastAPI is async but your Gmail client and DB calls need to be async-compatible too (use `asyncpg` not `psycopg2`, use `httpx` not `requests`)

---

### 3.2 LangGraph (Orchestration)

**What it is:** LangGraph is a library by LangChain for building **stateful, cyclical AI pipelines** as directed graphs. Each node is a processing step. Edges define flow. State is passed through the graph.

**Why it fits here:**
Your email processing pipeline is naturally a graph:
```
Fetch → Preprocess → Rules → LLM → Confidence Check → Policy → Action
```
LangGraph lets you model this exactly, including **conditional edges** (e.g., if confidence < 0.5, route to human review instead of action).

**Key concepts:**
- `StateGraph` — defines your pipeline as a graph
- `add_node(name, function)` — each processing step is a node
- `add_edge` / `add_conditional_edges` — wires nodes together with optional conditions
- `State` — a typed dictionary that passes accumulated data through the pipeline
- `Checkpointing` — LangGraph can save pipeline state to DB, letting you resume interrupted processing

**Honest assessment:**
For Phase 1–2, you don't need LangGraph. A plain Python function pipeline is simpler. Introduce LangGraph in Phase 3–4 when you need conditional routing and the pipeline becomes non-linear. Your PDR is right to list it, but don't start with it.

---

### 3.3 Gmail API (Google)

**What it is:** Google's REST API for reading, labeling, moving, and managing Gmail. Requires OAuth2 authentication.

**Key concepts you'll use:**

| Concept | What it does |
|---|---|
| **OAuth2 flow** | User grants your app permission; you get access + refresh tokens |
| **`messages.list`** | List email IDs matching a query (e.g., `is:unread after:2024/01/01`) |
| **`messages.get`** | Fetch full email content by ID (headers, body, parts) |
| **`messages.modify`** | Add/remove labels |
| **`messages.trash`** | Move to trash (reversible) |
| **`labels.create`** | Create new Gmail labels programmatically |
| **History API** | Track changes since last sync — this is how you do incremental sync |
| **Push Notifications** | Gmail pushes new email events to your server via Google Cloud Pub/Sub |

**Incremental Sync — the right way:**
Gmail's **History API** tracks all changes (new messages, label changes) since a `historyId`. You save the last `historyId` after each sync and only fetch changes since then. This is far more efficient than polling `messages.list` every time.

**MIME parsing:**
Gmail returns emails in MIME format — a nested tree of parts. You'll write a parser to extract plain text, detect HTML parts, and identify attachments. This is trickier than it looks because MIME nesting is inconsistent across email clients.

---

### 3.4 PostgreSQL + SQLAlchemy + Alembic

**PostgreSQL:** Relational database. Stores emails, feedback, rules, action logs.

**SQLAlchemy:** Python ORM. Lets you define tables as Python classes and query them without raw SQL.

**Key features:**
- `declarative_base()` — define models as Python classes
- `Session` — unit of work pattern for DB transactions
- `relationship()` — define foreign keys between models (Email → Feedback)
- `AsyncSession` — async-compatible sessions for use with FastAPI

**Alembic:** Database migration tool. Tracks schema changes as versioned files. When you add a column, you create a migration rather than manually altering the table. This is essential for a project that evolves.

**Honest assessment for personal use:**
Start with **SQLite** (zero setup, file-based). SQLAlchemy works identically with both. Migrate to PostgreSQL only when you need concurrent writes or your DB grows large.

---

### 3.5 Redis + Celery (Task Queue)

**Redis:** An in-memory key-value store. Used here as a **message broker** — Celery sends tasks to Redis, workers pick them up.

**Celery:** Python distributed task queue. Lets you run functions asynchronously in the background.

**Why you need this:**
When a new email arrives, you don't want the HTTP request to wait while the LLM classifies it (that could take 3–5 seconds). Instead: receive email → push classification task to Redis → immediately return HTTP 202 → Celery worker processes it asynchronously.

**Key features:**
- `@celery.task` — turns a Python function into a background task
- `task.delay(args)` — send the task to the queue (non-blocking)
- `task.apply_async(countdown=300)` — schedule task to run in 5 minutes
- `celery beat` — built-in scheduler for periodic tasks (your "run every 5 minutes" requirement)
- `task retries` — automatically retry failed tasks with exponential backoff

---

### 3.6 LLM Integration (OpenAI / Ollama)

**OpenAI API:**
- `gpt-4o-mini` is your best bet — fast, cheap, highly accurate for classification
- Use the `response_format: { type: "json_object" }` parameter to force JSON output
- Set `temperature: 0.0` for determinism (your PDR correctly identifies this)
- Use `system` prompt for role definition + output schema, `user` prompt for the email content

**Ollama (Local LLMs):**
- Runs models like `llama3`, `mistral`, `phi3` locally on your machine
- Zero API cost, complete privacy, no rate limits
- Slower than OpenAI on CPU; fast on Apple Silicon or NVIDIA GPU
- Use `llama3.1:8b` or `phi3:medium` for a good accuracy/speed tradeoff
- Ollama exposes an OpenAI-compatible API, so you can switch between them by just changing the base URL

**Which to choose:**
Use OpenAI for Phase 2 (faster to get working). Add Ollama as an alternative in Phase 4. Abstract the LLM call behind an interface so switching is one config change.

---

### 3.7 Next.js + React (Frontend)

**Next.js:** React framework with server-side rendering, API routes, and file-based routing.

**Why Next.js over plain React:**
- Server Components can pre-fetch email data before render (faster initial load)
- API Routes let you add lightweight backend endpoints without a separate server for simple operations
- Built-in TypeScript support

**Key libraries you'll use:**
- `TanStack Query (React Query)` — data fetching, caching, background refetch for the email queue
- `Recharts` or `Chart.js` — for your metrics visualization
- `shadcn/ui` or `Tailwind UI` — pre-built, well-designed components (email cards, badges, modals)
- `Zustand` — lightweight state management (simpler than Redux for this scale)

**Honest alternative:**
If you want to ship the dashboard faster, build it with **Streamlit** (Python). You write a Python file and get a working UI in hours. Rebuild in Next.js later if you want it polished. This is a valid choice for a personal tool.

---

## 4. Feature & Function Breakdown

### 4.1 The Email Object — Your Central Data Structure

Everything in the system passes around a normalized email object. Getting this schema right early is critical because changing it later breaks the pipeline.

**Fields to capture:**

| Field | Type | Source | Notes |
|---|---|---|---|
| `email_id` | string | Gmail | `msg.id` from API |
| `thread_id` | string | Gmail | Groups conversation threads |
| `subject` | string | MIME header | |
| `sender_name` | string | MIME header | Parse from "Name <email>" format |
| `sender_email` | string | MIME header | |
| `sender_domain` | string | Derived | `@gmail.com` extracted from sender |
| `recipients` | list | MIME header | To, CC |
| `body_plain` | string | MIME body | Prefer plain text over HTML |
| `body_html` | string | MIME body | Store raw for reference |
| `body_cleaned` | string | Preprocessing | What the classifier actually sees |
| `has_attachment` | bool | MIME parts | Critical for safety policy |
| `attachment_names` | list | MIME parts | |
| `received_at` | datetime | MIME header | |
| `labels` | list | Gmail | Current Gmail labels |
| `snippet` | string | Gmail | 100-char preview |

---

### 4.2 The Rule Engine — First Line of Defense

Rules run before the LLM and are deterministic. A well-tuned rule engine handles 60–70% of emails cheaply.

**Types of rules you can implement:**

| Rule Type | Example | How to implement |
|---|---|---|
| **Sender domain match** | `@linkedin.com → PROMOTIONAL` | String contains check |
| **Sender exact match** | `alerts@bankname.com → BANKING` | Set lookup |
| **Subject keyword** | `"OTP"`, `"statement"` → BANKING | Regex or keyword list |
| **Subject pattern** | `"Re:"` or `"Fwd:"` → maybe IMPORTANT | Regex |
| **Unsubscribe link** | Email has unsubscribe link → PROMOTIONAL | HTML parser check |
| **Attachment type** | `.pdf` attachment from bank domain → BANKING | MIME + domain combo |
| **List-Unsubscribe header** | Email header contains `List-Unsubscribe` → PROMOTIONAL | Header check |

**Rule priority:** Rules should have a priority number. Higher priority rules win conflicts. Store rules in DB so you can add/edit without redeploying.

---

### 4.3 The LLM Classifier — Second Line

Only emails that pass through rules without a confident match reach the LLM.

**Prompt structure:**
1. System prompt: Define your role, the 5 categories with descriptions, the exact JSON schema you expect
2. User prompt: The cleaned email (subject + sender + body, truncated to ~500 tokens)

**Confidence score:**
The LLM doesn't naturally return a calibrated confidence score — it returns a number that sounds confident. Your confidence filter should:
- Treat scores > 0.85 as "auto-act eligible"
- Treat scores 0.60–0.85 as "queue for human review"
- Treat scores < 0.60 as "hold, do nothing"

**Prompt versioning:**
Store your prompts as versioned files in `docs/prompt_library.md`. When you update a prompt, you'll want to know which prompt version classified which email (for debugging regressions).

---

## 5. The Gmail Integration Layer

### OAuth2 Flow — How it works end-to-end

1. Your app redirects the user to Google's OAuth consent screen
2. User approves → Google redirects back to your callback URL with a `code`
3. Your app exchanges the `code` for an `access_token` (short-lived, ~1 hour) and `refresh_token` (long-lived)
4. Store both tokens encrypted in your DB or a local secrets file
5. When `access_token` expires, use `refresh_token` to get a new one automatically

**Google Cloud Console setup (you'll need to do this):**
- Create a project
- Enable Gmail API
- Create OAuth 2.0 credentials (Web Application type)
- Add `http://localhost:8000/auth/callback` as authorized redirect URI
- Download the credentials JSON

### Scopes — Only request what you need

| Scope | What it allows | Do you need it? |
|---|---|---|
| `gmail.readonly` | Read emails | Yes |
| `gmail.modify` | Label, archive, move | Yes |
| `gmail.labels` | Create/delete labels | Yes |
| `gmail.metadata` | Headers only, no body | For sync efficiency |

Do **not** request `gmail.compose` or `gmail.send` — you don't need them and users (yourself) should be suspicious of apps that do.

---

## 6. The AI Classification Engine

### Pipeline Architecture

```
Email Object
     ↓
Rule Engine  ──→ [Rule Match Found?] ──YES──→ Skip LLM, assign category + confidence=1.0
     ↓ NO
Preprocessor (clean + truncate body)
     ↓
LLM Classifier
     ↓
Response Parser (extract JSON, validate schema)
     ↓
Confidence Filter
     ├── High confidence (>0.85)  →  Policy Layer
     ├── Medium (0.60–0.85)       →  Queue for human review
     └── Low (<0.60)              →  Hold, flag for manual classification
```

### Handling LLM Failures

LLMs occasionally return malformed JSON, timeout, or give nonsensical results. Your parser needs to handle:
- JSON parse errors → fallback to human review, log the raw response
- Missing fields → treat as low confidence
- Invalid category names → reject and fallback
- Timeout → retry once, then fallback

Never let an LLM error propagate to an action on the email. Fail safe = do nothing.

---

## 7. The Policy & Safety Layer

### Hard Rules (non-negotiable, always enforced)

These run on every email, regardless of classification confidence:

| Rule | Reason |
|---|---|
| Never permanently delete in v1 | Irreversible action = highest risk |
| Never trash emails with attachments automatically | Attachments are harder to recover |
| Never trash emails received in last 24 hours | Recency bias — could be important |
| Never act on emails marked with existing important label | User manually marked it |
| Never trash if sender is in contacts list | Implies known relationship |
| Cap auto-trash at N emails per hour | Prevents runaway deletion bugs |

### Soft Rules (configurable thresholds)

These live in your settings and can be adjusted:
- Confidence threshold for auto-action (default: 0.85)
- Confidence threshold for human review queue (default: 0.60)
- Maximum emails to process per run
- Categories that can never be auto-acted on (e.g., you may want IMPORTANT to always require review)

---

## 8. The Feedback & Learning Loop

### Why This Is Your Most Important Feature

The classifier starts at maybe 70–80% accuracy. It reaches 90%+ only through feedback. Every correction you make is a training signal. Without the feedback loop, you have a static tool. With it, you have a system that improves.

### The Review Queue — What to show

For each email pending review, show:
- Email subject + sender + date
- Body preview (first 200 chars of cleaned body)
- Predicted category (with color badge)
- Confidence bar (visual)
- Reasoning (the LLM's explanation — this is your transparency mechanism)
- Buttons: ✅ Approve | ✏️ Change Category | ⭐ Always Important | 🚫 Never Match This Rule

### What to store per feedback event

```
email_id          → which email
predicted         → what the system said
actual            → what you corrected it to
confidence        → the system's confidence at time of prediction
correction_source → "user_override" | "rule_match_error" | "llm_error"
timestamp
notes             → optional free text field (why did you override?)
```

### The Learning Mechanism

You are **not** fine-tuning an LLM (that's expensive and complex). Instead:
1. Accumulate feedback data over weeks
2. Run `pattern_analyzer.py` periodically to find patterns in corrections
3. `rule_suggester.py` proposes new rules based on patterns ("Emails from @noreply.github.com are always PROMOTIONAL")
4. You review and approve rule suggestions → they get added to the rule engine
5. This is **human-guided learning**, not autonomous learning — consistent with your PDR's philosophy

---

## 9. The Dashboard (Frontend)

### Pages & Their Purpose

**Page 1: Review Queue (Main Page)**
- List of emails awaiting human decision
- Filterable by: category, confidence range, date
- Sortable by: confidence (ascending = most uncertain first)
- Batch actions: approve all high-confidence in a category

**Page 2: Analytics**
- Classification accuracy over time (requires ground truth from feedback)
- Category distribution pie chart (are you getting mostly PROMOTIONAL?)
- Confidence score distribution histogram
- Drift indicator: is TRASH% suddenly spiking?

**Page 3: Rules Manager**
- List all active rules
- Toggle rules on/off without deleting
- See how many emails each rule has matched (rule effectiveness)
- Add new rules manually
- View pending rule suggestions from the learning system

**Page 4: Action Log**
- Every action taken by the system with timestamp
- Undo button for each action (calls `undo_manager.py`)
- Filter by action type (labelled, archived, trashed)

### State Management in the Frontend

Use **React Query** (TanStack Query) for server state. It handles:
- Caching email queue data
- Background refetch every 30 seconds (so the queue updates without refresh)
- Optimistic updates (mark email as approved in UI immediately, sync with backend in background)
- Error recovery

Use **Zustand** for local UI state (which filters are active, which email is selected, modal open/close).

---

## 10. Database Design in Practice

### Expanded Table Design

**emails**
```
id              UUID        Primary key
gmail_id        TEXT        Unique, Gmail's message ID
thread_id       TEXT        Gmail thread ID
subject         TEXT
sender_email    TEXT
sender_name     TEXT
sender_domain   TEXT        Indexed — you'll filter by this often
body_cleaned    TEXT
has_attachment  BOOLEAN     Indexed — safety policy checks this
received_at     TIMESTAMP   Indexed
category        TEXT        IMPORTANT | BANKING | INTERNSHIP | PROMOTIONAL | TRASH | UNCLASSIFIED
confidence      FLOAT
classification_source  TEXT   "rule" | "llm" | "manual"
status          TEXT        "pending_review" | "approved" | "actioned"
created_at      TIMESTAMP
```

**feedback**
```
id              UUID
email_id        UUID        FK → emails.id
predicted       TEXT
actual          TEXT
confidence      FLOAT
timestamp       TIMESTAMP
notes           TEXT        Nullable
```

**rules**
```
id              UUID
name            TEXT
rule_type       TEXT        "sender_domain" | "keyword" | "header" | "regex"
rule_value      TEXT        The actual value (domain name, keyword, regex pattern)
target_category TEXT
priority        INTEGER     Higher = evaluated first
is_active       BOOLEAN
match_count     INTEGER     How many emails this rule has matched (increment on match)
created_at      TIMESTAMP
```

**action_log**
```
id              UUID
email_id        UUID        FK → emails.id
action_type     TEXT        "labelled" | "archived" | "trashed" | "starred"
action_detail   JSONB       The parameters used (label name, folder, etc.)
undone          BOOLEAN     Default false
timestamp       TIMESTAMP
```

**user_preferences**
```
key             TEXT        Unique
value           TEXT        JSON-serialized value
updated_at      TIMESTAMP
```

### Indexing Strategy

Index columns you filter or sort by frequently:
- `emails.sender_domain` — rule engine checks this
- `emails.status` — queue queries filter by this
- `emails.has_attachment` — safety policy
- `emails.received_at` — time-based queries
- `emails.category` — dashboard filters
- `feedback.email_id` — joining tables

---

## 11. Automation & Scheduling

### Two Approaches

**Option A: Polling (simpler, your PDR's approach)**
- Celery Beat runs a task every 5–10 minutes
- Task calls Gmail API: fetch emails since last sync
- Classify and act
- Update `last_sync_history_id` in DB
- Pros: Simple, works offline
- Cons: Up to 10-minute delay, constant API calls even when inbox is quiet

**Option B: Gmail Push Notifications (better, more complex)**
- Register a webhook with Gmail via Google Cloud Pub/Sub
- Gmail calls your endpoint when new emails arrive (real-time)
- You fetch only the changed emails via History API
- Pros: Real-time, no wasted API calls
- Cons: Requires public URL (use ngrok for dev), more infrastructure
- Consider this after Phase 3

### Recommended progression:
- Phase 1–2: Run manually via CLI command
- Phase 3: Add Celery Beat polling every 5 minutes
- Phase 4+: Optionally migrate to Push Notifications

### Failure Handling

Every scheduled task should:
1. Wrap execution in try/except
2. Log exceptions with full traceback
3. Retry up to 3 times with exponential backoff (Celery handles this)
4. Send an alert (print to log, or email yourself) if all retries fail
5. Never silently swallow errors

---

## 12. Development Phases — Practical Order

### Phase 1: Email Fetch + Manual CLI Classification (Week 1–2)

**Goal:** Fetch emails, display them, manually classify via terminal.

What to build:
- Gmail OAuth setup
- `gmail_client.py` — fetch emails
- `html_cleaner.py` — strip HTML
- Basic DB with `emails` table (SQLite)
- CLI script that shows email + asks "what category?" → stores answer

**Success criteria:** You can fetch your last 50 emails and manually label them via terminal.

---

### Phase 2: Rule Engine + LLM Classification (Week 3–4)

**Goal:** Automate classification without touching Gmail actions yet.

What to build:
- `rule_engine.py` with 10–15 starter rules
- `llm_classifier.py` with OpenAI integration
- `classifier_pipeline.py` stitching them together
- Classification results stored in DB (no actions yet)
- Simple CLI report: "Here's how I would have classified your last 50 emails"

**Success criteria:** System classifies emails with >75% accuracy on your manual labels from Phase 1.

---

### Phase 3: Dashboard + Feedback Loop (Week 5–7)

**Goal:** Make the system interactive and usable daily.

What to build:
- FastAPI backend with email queue + feedback endpoints
- Basic React/Next.js frontend (or Streamlit if you want speed)
- Review queue with approve/override functionality
- Feedback stored in DB
- `action_logger.py` — log every decision even if no Gmail action taken

**Success criteria:** You can review and approve classifications from a web UI. No Gmail actions yet.

---

### Phase 4: Action Engine + Safety Layer (Week 8–9)

**Goal:** Let the system act on emails (label, archive) for high-confidence decisions.

What to build:
- `gmail_actions.py` — label, archive via API
- `safety_checks.py` — all hard rules
- `policy_engine.py` — orchestrates safety checks before any action
- `undo_manager.py` — reverses actions using action log
- Undo button in dashboard

**Success criteria:** System automatically labels/archives emails above confidence threshold, with undo working.

---

### Phase 5: Monitoring + Full Automation (Week 10–12)

**Goal:** System runs continuously and improves over time.

What to build:
- Celery Beat scheduler
- `drift_detector.py` — alert on anomalies
- `pattern_analyzer.py` + `rule_suggester.py`
- Analytics page in dashboard
- Rules manager in dashboard

**Success criteria:** System runs every 5 minutes, you review queue once a day, accuracy is improving over weeks.

---

## 13. Key Decisions You Need to Make

These are architectural decisions where both options are valid — your choice will shape the codebase.

| Decision | Option A | Option B | Recommendation |
|---|---|---|---|
| **Database for v1** | PostgreSQL | SQLite | SQLite — migrate later |
| **LLM Provider** | OpenAI (fast, paid) | Ollama (free, local) | OpenAI for Phase 2, add Ollama option in Phase 4 |
| **Frontend speed** | Streamlit (Python, fast) | Next.js (professional) | Streamlit for Phase 3, rebuild in Next.js Phase 5 |
| **Scheduling** | Celery Beat (polling) | Gmail Push (real-time) | Celery for Phase 3, Push later |
| **Sync strategy** | Full fetch each time | History API incremental | Start full, migrate to History API in Phase 2 |
| **Confidence threshold** | Fixed (0.85) | Adaptive per category | Fixed first, make it configurable in Phase 4 |
| **Email storage** | Store full body in DB | Store only metadata, refetch body | Store cleaned body — fetching again costs API quota |

---

## 14. Common Pitfalls to Avoid

### 1. Classifying with the wrong context
LLMs classify better with a clean, short input. Sending a 5000-word newsletter to the LLM wastes tokens and reduces accuracy. Always truncate to 300–500 tokens of cleaned body.

### 2. Not versioning your prompts
Your classification prompt is part of your system. When you change it, your accuracy can change. Version it in git. Log which prompt version classified which email. Otherwise debugging regressions is impossible.

### 3. Trusting confidence scores from LLMs
LLMs are overconfident by default. A 0.95 confidence doesn't mean 95% accuracy. Calibrate your thresholds empirically against your actual feedback data, not against the LLM's self-reported confidence.

### 4. Building the action engine before the feedback loop
This is the most common mistake. If you wire up actions before you know your accuracy, you'll archive or label emails incorrectly with no way to measure it. Phase 3 (feedback) must come before Phase 4 (actions).

### 5. Forgetting about MIME complexity
Gmail's API returns emails in MIME format. A single email can have 10+ nested MIME parts (HTML, plain text, inline images, attachments). Your MIME parser needs to handle this robustly. Test it on forwarded emails and emails with multiple attachments.

### 6. Ignoring rate limits
Gmail API has a quota of 250 units per second and 1 billion units per day. Each `messages.get` call costs 5 units. Fetching 100 emails in a burst costs 500 units — fine normally, but add a small delay between batch requests to be safe.

### 7. Storing tokens insecurely
Your OAuth refresh token is the key to your entire Gmail inbox. Never store it in plain text in a file. Use environment variables, or encrypt it with a key derived from a master password.

### 8. Underestimating the backfill problem
You likely have thousands of old emails. Your system will be built to process new emails incrementally. Running it on historical backlog requires a separate batch script with rate limiting and restart capability. Plan for this separately.

---

## 🔑 The One Thing That Makes This System Work

Your PDR says it and it bears repeating:

> You're building a **decision-making system under uncertainty**.

The technical parts — Gmail API, LLM calls, FastAPI — are straightforward and well-documented. The hard part is building the **human-in-the-loop mechanism** that is genuinely usable, so you actually give it feedback, so it actually improves. If the review queue is painful to use, you'll stop reviewing. If you stop reviewing, the system never improves. If it never improves, you stop trusting it. If you stop trusting it, it just sits there.

**Design the review queue UX first. Make it so fast and satisfying to approve/correct emails that you actually want to do it.** That is what separates a project that works from a project that just runs.

---

*Guide version 1.0 — prepared against EmailBotPDR.md*
