
---

# 📄 Project Requirements Document

## 🧠 AI-Powered Email Intelligence & Management System

---

# 1. 🎯 Objective

Build a **semi-autonomous email management system** that:

* Classifies emails using **semantic understanding**
* Learns from **user feedback over time**
* Minimizes manual intervention
* Ensures **high safety (no accidental deletion)**
* Operates continuously on incoming emails

---

# 2. 🧩 Problem Statement

Users face:

* Large backlog of unread emails
* No clear rule-based filtering possible
* Important emails (internships, banking, personal) mixed with noise
* Limited time to manually curate rules

---

# 3. 🧠 Core Philosophy (Critical Design Principle)

> “AI assists decisions, but does not operate without constraints.”

---

# 4. 🏗️ System Overview

```text
Email Source → Processing Pipeline → Classification → Policy Layer → Action Engine → Feedback Loop
```

---

# 5. ⚙️ Functional Requirements

## 5.1 Email Ingestion

### Requirements:

* Fetch emails from Gmail (primary)
* Support:

  * Subject
  * Sender
  * Body
  * Attachments metadata

### Constraints:

* Must support incremental sync (not full fetch every time)

---

## 5.2 Preprocessing Layer

### Responsibilities:

* Clean email text
* Remove HTML noise
* Extract:

  * Keywords
  * Attachment presence
  * Sender domain

### Optional:

* LLM-based summarization for long emails

---

## 5.3 Classification Engine

### Input:

Structured email object

### Output:

```json
{
  "category": "IMPORTANT | BANKING | INTERNSHIP | PROMOTIONAL | TRASH",
  "confidence": 0.0 - 1.0,
  "reasoning": "short explanation"
}
```

---

### Classification Strategy:

#### Hybrid Model:

1. **Rule-Based Layer**
2. **LLM-Based Classification**
3. **Confidence Filtering**

---

### Categories Definition:

| Category    | Description                      |
| ----------- | -------------------------------- |
| IMPORTANT   | Personal, academic, deadlines    |
| BANKING     | Statements, transactions, alerts |
| INTERNSHIP  | Job offers, applications         |
| PROMOTIONAL | Marketing, newsletters           |
| TRASH       | Spam, irrelevant                 |

---

## 5.4 Policy Layer (Decision Control)

### Responsibilities:

* Override unsafe decisions
* Enforce system constraints

### Example Rules:

* Never delete if confidence < 0.9
* Never delete emails with attachments unless explicitly marked

---

## 5.5 Action Engine

### Actions:

| Category    | Action                             |
| ----------- | ---------------------------------- |
| IMPORTANT   | Label + Keep                       |
| BANKING     | Move to folder                     |
| INTERNSHIP  | Star + Label                       |
| PROMOTIONAL | Archive                            |
| TRASH       | Move to trash (with safety checks) |

---

## 5.6 Feedback System (Human-in-the-loop)

### Requirements:

* Show:

  * Email summary
  * Predicted category
  * Confidence
* Allow:

  * Approve
  * Modify category
  * Mark as “always important”

---

### Output Stored:

```json
{
  "email_id": "...",
  "predicted": "...",
  "actual": "...",
  "confidence": 0.72
}
```

---

## 5.7 Learning System

### Responsibilities:

* Analyze feedback data
* Extract patterns
* Suggest improvements (not auto-apply)

---

## 5.8 Monitoring & Analytics

### Metrics:

* Classification accuracy
* False positive rate
* Category distribution
* Drift detection

---

### Alerts:

* Sudden spike in TRASH classification
* Drop in confidence scores

---

# 6. 🏗️ System Architecture

## 6.1 High-Level Components

```text
Frontend (Dashboard)
        ↓
Backend API (FastAPI)
        ↓
Processing Engine (LangGraph)
        ↓
LLM + Rule Engine
        ↓
Database (PostgreSQL)
        ↓
Gmail API
```

---

## 6.2 Processing Flow

```text
1. Fetch Email
2. Preprocess
3. Apply Rules
4. LLM Classification
5. Confidence Check
6. Policy Validation
7. Execute Action
8. Store Result
```

---

# 7. 🧠 AI / LLM Requirements

## 7.1 Tasks:

* Email classification
* Email summarization
* Pattern extraction (offline)

---

## 7.2 Prompt Constraints:

* Must return structured JSON
* Must include reasoning
* Must be deterministic (low temperature)

---

## 7.3 Model Options:

* OpenAI GPT
* Local LLM (Llama via Ollama)

---

# 8. 🗄️ Database Design

## 8.1 Tables

### Emails

```sql
email_id
subject
sender
body
category
confidence
created_at
```

---

### Feedback

```sql
id
email_id
predicted_category
actual_category
confidence
timestamp
```

---

### Rules

```sql
id
rule_definition
priority
created_at
```

---

# 9. 🧑‍💻 Dashboard Requirements

## Features:

* Email review queue
* Filter by:

  * Low confidence
  * Category
* Actions:

  * Approve
  * Edit classification
* Metrics visualization

---

# 10. ⚠️ Safety Requirements (CRITICAL)

* No permanent deletion in v1
* Trash retention period (e.g., 30 days)
* Action logs must be stored
* Undo functionality required

---

# 11. 🔄 Automation Requirements

* Run every 5–10 minutes
* Process only new emails
* Retry on failure

---

# 12. 🚀 Non-Functional Requirements

## Performance:

* Process email < 2 seconds

## Reliability:

* 99% uptime

## Scalability:

* Handle 10k+ emails

## Security:

* OAuth2 for Gmail
* Encrypted token storage

---

# 13. 🔧 Tech Stack

## Backend:

* Python (FastAPI)

## Orchestration:

* LangGraph

## AI:

* OpenAI / Ollama

## Database:

* PostgreSQL

## Queue:

* Redis + Celery

## Frontend:

* Next.js / React

---

# 14. 📈 Development Roadmap

## Phase 1:

* Email fetch + CLI classification

## Phase 2:

* LLM integration

## Phase 3:

* Dashboard + feedback loop

## Phase 4:

* Rule layer

## Phase 5:

* Monitoring + automation

---

# 15. 🧪 Testing Strategy

* Unit tests for rules
* Mock LLM responses
* Simulated email datasets
* Edge case testing

---

# 16. ⚠️ Risks & Mitigation

| Risk                 | Mitigation                           |
| -------------------- | ------------------------------------ |
| Wrong classification | Confidence threshold + human review  |
| Over-deletion        | No delete in v1                      |
| Model inconsistency  | Low temperature + structured prompts |
| Drift                | Monitoring + retraining              |

---

# 17. 🔥 Future Enhancements

* Multi-email provider support
* Personalization models
* Auto-priority scoring
* Smart reply suggestions

---

# 🧠 Final Reality Check

You’re not just building a tool.
You’re building:

> A **decision-making system under uncertainty**

That means your real challenge is:

* not classification
* but **trust calibration over time**

