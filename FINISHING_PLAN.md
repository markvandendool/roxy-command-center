# ROXY Command Center - Master Finishing Plan
**Created**: 2026-01-09
**Updated**: 2026-01-09 (Chief's Master Architecture)
**Status**: ACTIVE

---

## 🎯 NORTH STAR

**Home = Roxy Console (Talk + Triage + Execute)**

The Command Center is an **operations console**, NOT a stats dashboard.

1. **Talk to Roxy** - Conversation is the command line
2. **Triage Inbox** - Everything needing a response in one list
3. **Execute** - Progressions/runs are objects you point Roxy at

**Key Principle**: GTK stays thin. It calls one `roxy-core` endpoint and renders state.

---

## 📐 HOME SCREEN LAYOUT (Progressive Disclosure)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  [ROXY]  Mode: Local │ GPU0: 38°C │ GPU1: 56°C │ CPU: 6% │ ⚙️ Settings │
├──────────────────┬─────────────────────────────┬────────────────────────┤
│                  │                             │                        │
│  B. UNIFIED      │  A. ROXY CONVERSATION       │  C. PROGRESSIONS /     │
│     INBOX        │     (primary)               │     EXECUTION TIMELINE │
│     (triage)     │                             │     (action lane)      │
│                  │  Context chips:             │                        │
│  Identity:       │  • Current focus: MindSong  │  Active Runs:          │
│  [👤 Me] [🎵 ]   │  • Active project: CC       │  ┌──────────────────┐  │
│                  │  • Recent alerts: 1         │  │ ▶ Deploy v2.1    │  │
│  Buckets:        │  • Waiting on: API resp     │  │   [Run] [Logs]   │  │
│  [Now] [Queued]  │                             │  └──────────────────┘  │
│  [FYI]           │  ┌─────────────────────┐    │  ┌──────────────────┐  │
│                  │  │ Roxy: I found 3     │    │  │ ✓ Backup DB      │  │
│  ┌────────────┐  │  │ issues in the repo  │    │  │   done 2m ago    │  │
│  │ 🔴 Mom SMS │  │  └─────────────────────┘    │  └──────────────────┘  │
│  │ Hey did... │  │  ┌─────────────────────┐    │  ┌──────────────────┐  │
│  │ [Reply]    │  │  │ You: Check GPU and  │    │  │ ⏳ Content pub   │  │
│  │ [Defer]    │  │  │ deploy the fix      │    │  │   queued (3)     │  │
│  │ [→Roxy]    │  │  └─────────────────────┘    │  │   [▶] [Cancel]   │  │
│  └────────────┘  │                             │  └──────────────────┘  │
│  ┌────────────┐  │  Mode: [Draft] [Send]       │                        │
│  │ 🟡 GitHub  │  │  (human-in-the-loop toggle) │  Alerts:               │
│  │ PR #142... │  │                             │  ┌──────────────────┐  │
│  └────────────┘  │  [🎤 Talk] [___________]    │  │ ⚠ GPU1 > 55°C    │  │
│                  │  [Send]                     │  │ [→ Now] [Dismiss]│  │
│  SUPER REPLY:    │                             │  └──────────────────┘  │
│  [___________]   │                             │                        │
│  [📧][💬][🐙]   │                             │  [Open Full Logs]      │
│  [Send]          │                             │                        │
└──────────────────┴─────────────────────────────┴────────────────────────┘
```

### A. Roxy Conversation (Center, Primary)
- Always-on chat transcript (streaming)
- Big **Talk** button (push-to-talk / click-to-record) + mute/stop
- **"Roxy Draft" vs "Roxy Send"** modes (human-in-the-loop toggle)
- Context chips: Current focus, Active project, Recent alerts, Waiting on…

### B. Unified Inbox / Notifications (Left, Triage Lane)
- One list for **everything that needs a response**:
  - Messages, mentions, DMs, comments, emails, tickets, calendar pings, alerts
- **Three buckets** (progressive disclosure):
  - **Now** (requires reply) / **Queued** (can wait) / **FYI** (no reply needed)
- **Identity filter**: `[👤 Me]` `[🎵 MindSong]` `[📬 All]`
- One-click actions per item:
  - **Reply**, **Quick reaction**, **Defer**, **Assign to Roxy**, **Turn into task**
- **Super reply bar**: Type once, choose channel(s), send

### C. Progressions / Execution Timeline (Right, Action Lane)
- Timeline of active "runs" (orchestrator jobs, content pipeline, mirrors)
- Big buttons: **Run / Resume / Cancel**, **Open logs**, **Promote to 'Now'**
- Every inbox item can become a **Progression** (runnable playbook)
- Every Progression emits an **ExecutionRun** timeline entry

---

## 🏗️ SYSTEM ARCHITECTURE: One Canonical Event Stream

To make "20 different sources" sane, everything becomes a single internal format.

### Core Objects (Canonical Schema)

```python
# Thread (who/what/where)
Thread {
    id: UUID
    platform: str           # "github", "email", "instagram", etc.
    external_id: str        # Platform's conversation/thread ID
    identity: str           # "mark" or "mindsong" (which identity owns this)
    participants: list[Contact]
    last_activity: datetime
    status: str             # "active", "archived", "snoozed"
    bucket: str             # "now", "queued", "fyi"
    metadata: dict
}

# Message (the actual content)
Message {
    id: UUID
    thread_id: UUID
    direction: str          # "inbound" or "outbound"
    sender: Contact
    content: str
    attachments: list
    timestamp: datetime
    roxy_draft: str?        # AI-generated reply draft
    sent_via: str?          # Which channel was used to send
}

# Notification (mentions, alerts, FYIs)
Notification {
    id: UUID
    source: str             # "github", "grafana", "n8n", etc.
    type: str               # "mention", "alert", "fyi", "deadline"
    title: str
    body: str
    link: str?
    priority: str           # "critical", "high", "normal", "low"
    requires_action: bool
    acknowledged: bool
}

# ExecutionRun (progressions/orchestrator state)
ExecutionRun {
    id: UUID
    name: str
    type: str               # "orchestrator", "content_pipeline", "deployment"
    status: str             # "queued", "running", "completed", "failed", "cancelled"
    started_at: datetime?
    completed_at: datetime?
    progress_pct: int?
    logs_url: str
    can_cancel: bool
    can_rollback: bool
}

# Contact (CRM identity map across platforms)
Contact {
    id: UUID
    display_name: str
    identities: dict        # {"github": "username", "email": "x@y.com", ...}
    is_me: bool             # One of my identities?
    my_identity: str?       # If is_me, which one? "mark" or "mindsong"
    notes: str?
}

# Action (what the user/Roxy can do)
Action {
    type: str               # "reply", "like", "schedule", "publish", "execute", "snooze"
    target_id: UUID         # Thread, Message, or ExecutionRun
    payload: dict
    executed_by: str        # "user" or "roxy"
    requires_approval: bool
}
```

### Pipeline Architecture

```
CONNECTORS                    EVENT BUS              STORAGE        UI
─────────────────────────────────────────────────────────────────────────
Email (IMAP)         ─┐                         
GitHub (Webhooks)    ─┤       NATS JetStream        ┌─────────┐
Discord (Bot)        ─┤  ─→   inbox.events     ─→   │Postgres │ ─→  GTK4
Instagram (API)      ─┼─→     inbox.actions    ─→   │ (truth) │     App
Twitter (API)        ─┤       runs.status           └─────────┘
YouTube (API)        ─┤                                  │
Ops Alerts           ─┘                                  │
                                                         ▼
                           n8n subscribes ──────→  Automation
                           (auto-triage,           (Roxy drafts,
                            SLA monitoring,         escalation,
                            Roxy drafts)            templates)
```

### roxy-core Inbox API

GTK app calls **one service**. roxy-core handles complexity internally.

```
GET  /api/inbox/threads              # List threads (filterable by identity, bucket, source)
GET  /api/inbox/threads/:id          # Get thread with messages
POST /api/inbox/threads/:id/reply    # Send reply (routes to correct connector)
POST /api/inbox/threads/:id/action   # Archive, snooze, assign-to-roxy, convert-to-task

GET  /api/notifications              # List notifications
POST /api/notifications/:id/ack      # Acknowledge

GET  /api/runs                       # List execution runs
POST /api/runs/:id/dispatch          # Start/resume
POST /api/runs/:id/cancel            # Cancel
GET  /api/runs/:id/logs              # Stream logs
```

Internally, roxy-core talks to:
- **NATS** (event bus)
- **Postgres** (canonical store)
- **n8n** (automation workflows)
- **Podium/Orchestrator** (dispatch & run streaming)

---

## 📊 PHASED BUILD PLAN

### Phase 0: Telemetry Trust ✅ COMPLETE
**Goal**: Never wonder if data is flowing

- [x] normalize_status() function
- [x] Debug strip in header
- [x] Console logging for poll/update cycle
- [x] CPU/GPU cards update every second
- [x] Git commit: `29009d8`

---

### Phase 1: Roxy Console v1 — Home Becomes Useful Daily (1-2 weeks)
**Goal**: Core cockpit functionality - chat + progressions + notification shell

**Deliverables**:
- [ ] **Roxy Chat Pane** (center)
  - Text input with send button
  - Scrollable chat history (streaming)
  - Talk button (voice placeholder → wyoming later)
  - "Draft vs Send" mode toggle
  - Context chips row
  
- [ ] **Progressions Panel** (right)
  - List of active/recent runs
  - Each card: name, status, [▶ Run] [📋 Logs] [⏹ Cancel]
  - Dispatch button → `POST /api/runs/:id/dispatch`
  - Live status updates (queued → running → done)
  
- [ ] **Notifications Shell** (left)
  - "Now / Queued / FYI" bucket tabs (stub)
  - Identity filter chips: [👤 Me] [🎵 MindSong] [All]
  - Hardcoded test items initially
  - Alerts escalation: "→ Now" button

**Success Criteria**:
- Can type to Roxy and get streaming response
- Can dispatch a progression and watch status change
- Three-column layout working with proper sizing

---

### Phase 2: Unified Inbox v0 — 3 Sources, End-to-End (2-3 weeks)
**Goal**: Real messages from real sources, can reply from Command Center

**Sources (pick 3)**:
| Source | Integration | Priority | Why |
|--------|-------------|----------|-----|
| Email | IMAP + SMTP | P0 | Easy win, everyone has it |
| GitHub | Webhooks + API | P0 | Already integrated, high value |
| Discord | Bot | P0 | Community active there |

**Deliverables**:
- [ ] **Inbox Service** in roxy-core
  - `GET /api/inbox/threads` endpoint
  - `POST /api/inbox/threads/:id/reply` endpoint
  - Thread schema in Postgres
  
- [ ] **Connectors**
  - Email connector (IMAP poll + SMTP send)
  - GitHub connector (webhooks for notifications)
  - Discord connector (bot for DMs/mentions)
  
- [ ] **GTK Inbox Widget**
  - Thread list with source icons
  - Preview on click
  - Reply composer
  - Route reply through correct connector
  
- [ ] **NATS Topics**
  - `inbox.events` (new messages)
  - `inbox.actions` (replies, archive, etc.)

**Success Criteria**:
- Inbox shows messages from 3 sources
- Can reply to an email from Command Center
- Reply actually sends via correct platform

---

### Phase 3: Unified Inbox v1 — 6-10 Sources + Identity + Roxy Drafts (3-4 weeks)
**Goal**: Identity mapping works, Roxy helps draft replies

**Add Sources**:
| Source | Integration | Priority |
|--------|-------------|----------|
| Instagram DMs/comments | Official API | P1 |
| YouTube comments | API | P1 |
| X/Twitter | API v2 | P1 |
| Slack | Bot | P2 |
| Telegram | Bot | P2 |

**Deliverables**:
- [ ] **Identity Mapping**
  - Each thread tagged with identity
  - Filter chips work
  - Reply routes through correct identity's account
  
- [ ] **Roxy Draft Reply**
  - n8n workflow: new message → Roxy generates draft
  - Draft stored in `Message.roxy_draft`
  - UI shows draft with [Approve] [Edit] [Reject]
  
- [ ] **Reply Templates/Macros**
  - Common responses saved
  - Quick-insert from picker
  
- [ ] **Contact Unification**
  - Same person across platforms → one Contact
  - CRM notes field

**Success Criteria**:
- Can filter inbox by identity (Me vs MindSong)
- Roxy drafts appear for new messages
- One-click approve sends draft

---

### Phase 4: Unified Inbox v2 — Automation + Metrics (4-6 weeks)
**Goal**: n8n automation, SLA tracking, "Roxy handles it" mode

**Deliverables**:
- [ ] **n8n Automation Workflows**
  - Auto-triage: route by keywords/sender
  - Auto-respond: templates for common queries
  - Escalation: urgent → "Now" bucket + alert
  
- [ ] **Policy Rules**
  - "If X → draft + schedule"
  - "If urgent → notify + pin to Now"
  - "If from VIP → always Now"
  
- [ ] **Metrics Dashboard**
  - Response time by source
  - Backlog depth
  - Automation success rate
  - Unread aging
  
- [ ] **"Roxy Can Handle It" Mode**
  - Per-thread arming (explicit opt-in)
  - Audit trail of all auto-actions
  - Rollback capability

**Success Criteria**:
- Routine messages handled automatically
- Response time metrics visible
- Can arm Roxy on specific threads

---

### Phase 5: 20-Source Expansion + iMessage (Gated)
**Goal**: Full coverage, including the hard ones

**Only start after Phase 4 is stable.**

**Add Sources**:
| Source | Integration | Difficulty |
|--------|-------------|------------|
| WhatsApp Business | Official API | Medium |
| LinkedIn | Limited API | Hard |
| Reddit | API | Medium |
| SMS | Twilio | Easy |
| iMessage | Mac relay | Hard |

**iMessage Reality Check**:
- Apple has NO official iMessage server API
- Requires always-on Mac running relay (BlueBubbles, AirMessage, etc.)
- Unofficial, fragile, may break with macOS updates
- **Treat as "gated connector" with explicit reliability expectations**

**Plan Stance**:
- Don't block whole inbox on iMessage
- Implement as special connector with manual fallback path
- Accept: this could break at any time

**Success Criteria**:
- 15+ sources working reliably
- iMessage working (with reliability caveats documented)
- System stable under load

---

## 🔧 PROGRESSIONS INTEGRATION

### Shared "Dispatch" Model with MindSong /progress

The Command Center and MindSong share the same orchestration philosophy:

```
Inbox Item → "Turn into task" → Creates Progression → Dispatch → ExecutionRun
```

**Key Constraint**: Command Center does NOT implement execution logic itself.
It calls **one roxy-core `dispatch/execute` endpoint** and renders state.

### Roxy Can Propose Actions

For any inbox item, Roxy can suggest:
- "Reply with template X"
- "Queue a follow-up in 3 days"
- "Kick off pipeline job"
- "Escalate / create ticket / log CRM note"
- "Mark as FYI / Archive"

### ExecutionRun States

```
queued → running → completed
                 → failed
                 → cancelled
```

---

## 📋 ALL 20 MESSAGE SOURCES (Placeholder Status)

**All 20 sources available for BOTH identities. APIs/accounts to be wired up soon.**

| # | Source | 👤 Me | 🎵 MindSong | Integration | Status |
|---|--------|-------|-------------|-------------|--------|
| 1 | Email (personal) | ✅ | - | IMAP/SMTP | 🔲 Placeholder |
| 2 | Email (business) | - | ✅ | IMAP/SMTP | 🔲 Placeholder |
| 3 | SMS | ✅ | ✅ | Twilio | 🔲 Placeholder |
| 4 | iMessage | ✅ | - | Mac relay | 🔲 Placeholder (Phase 5) |
| 5 | GitHub | ✅ | ✅ | Webhooks + API | 🔲 Placeholder |
| 6 | Discord | ✅ | ✅ | Bot | 🔲 Placeholder |
| 7 | Slack | ✅ | ✅ | Bot | 🔲 Placeholder |
| 8 | Telegram | ✅ | ✅ | Bot API | 🔲 Placeholder |
| 9 | WhatsApp | ✅ | ✅ | Business API | 🔲 Placeholder |
| 10 | Instagram DMs | - | ✅ | Graph API | 🔲 Placeholder |
| 11 | Instagram Comments | - | ✅ | Graph API | 🔲 Placeholder |
| 12 | YouTube Comments | - | ✅ | Data API v3 | 🔲 Placeholder |
| 13 | X/Twitter DMs | ✅ | ✅ | API v2 | 🔲 Placeholder |
| 14 | X/Twitter Mentions | ✅ | ✅ | API v2 | 🔲 Placeholder |
| 15 | LinkedIn | ✅ | ✅ | Limited API | 🔲 Placeholder |
| 16 | Reddit | ✅ | ✅ | API | 🔲 Placeholder |
| 17 | Twitch Chat | - | ✅ | API | 🔲 Placeholder |
| 18 | Signal | ✅ | - | Bridge | 🔲 Placeholder (Phase 5) |
| 19 | Matrix | ✅ | ✅ | Native | 🔲 Placeholder |
| 20 | RSS/Newsletters | ✅ | ✅ | Feed parser | 🔲 Placeholder |

### System Sources (Always MindSong Identity)
| Source | Integration | Status |
|--------|-------------|--------|
| Ops Alerts (Grafana) | Webhooks | 🔲 Placeholder |
| Orchestrator Events | NATS | 🔲 Placeholder |
| StackKraft Pipeline | NATS | 🔲 Placeholder |
| Service Health | roxy-core | 🔲 Placeholder |

Each state transition is an event on `runs.status` NATS topic.

---

## 📋 TOP 20 MESSAGE SOURCES (Prioritized)

### Tier 1: Phase 2 (Must Have - Do First)
| # | Source | API Method | Identity | Notes |
|---|--------|------------|----------|-------|
| 1 | Email (personal) | IMAP/SMTP | 👤 Me | Fast win |
| 2 | Email (business) | IMAP/SMTP | 🎵 MindSong | Business comms |
| 3 | GitHub | Webhooks + API | 🎵 MindSong | PRs, issues, mentions |
| 4 | Discord | Bot | 🎵 MindSong | Community |
| 5 | Ops Alerts | Grafana/webhooks | 🎵 MindSong | FYI → "Now" escalation |

### Tier 2: Phase 3 (High Value - Monetization Loop)
| # | Source | API Method | Identity | Notes |
|---|--------|------------|----------|-------|
| 6 | Instagram DMs | Graph API | 🎵 MindSong | Monetization |
| 7 | YouTube comments | Data API v3 | 🎵 MindSong | Engagement |
| 8 | X/Twitter | API v2 | 🎵 MindSong | Tech community |
| 9 | Slack | Bot | 🎵 MindSong | If collaborating |
| 10 | Telegram | Bot | Either | Depends on use |

### Tier 3: Phase 4 (Expand Coverage)
| # | Source | API Method | Identity | Notes |
|---|--------|------------|----------|-------|
| 11 | WhatsApp Business | Official API | 🎵 MindSong | If needed |
| 12 | LinkedIn | Limited API | 🎵 MindSong | Professional |
| 13 | Reddit | API | 🎵 MindSong | r/LocalLLaMA etc |
| 14 | Twitch chat | API | 🎵 MindSong | If streaming |
| 15 | SMS | Twilio | 👤 Me | Personal |

### Tier 4: Phase 5 (Gated/Hard)
| # | Source | API Method | Identity | Notes |
|---|--------|------------|----------|-------|
| 16 | iMessage | Mac relay | 👤 Me | Fragile |
| 17 | Signal | Bridge | 👤 Me | Privacy contacts |
| 18 | Teams | API | Either | If corporate |
| 19 | Matrix | Native | Either | If using Matrix backbone |
| 20 | RSS/Newsletters | Feed parser | Either | FYI bucket |

---

## ✅ SUCCESS CRITERIA

### Phase 1 Complete When:
- [ ] Can type to Roxy and get streaming response in chat pane
- [ ] Progressions list shows at least 3 items
- [ ] Dispatch button triggers execution
- [ ] Status updates from queued → running → done
- [ ] Three-column layout renders correctly
- [ ] Identity filter chips visible (even if not functional)

### Phase 2 Complete When:
- [ ] Inbox shows messages from 3+ sources (Email, GitHub, Discord)
- [ ] Can reply from Command Center
- [ ] Reply routes through correct connector (actually sends)
- [ ] Threads grouped by conversation
- [ ] Basic audit trail in Postgres

### Phase 3 Complete When:
- [ ] Identity filtering works (Me vs MindSong)
- [ ] "Roxy Draft" generates AI response for new messages
- [ ] One-click approve sends draft
- [ ] 6+ sources integrated
- [ ] Contact unification working

### Phase 4 Complete When:
- [ ] n8n automation rules executing
- [ ] Response time metrics visible
- [ ] "Roxy handles it" mode working with audit trail
- [ ] 10+ sources integrated

### Phase 5 Complete When:
- [ ] 15+ sources working reliably
- [ ] iMessage working (with caveats)
- [ ] System stable for 30 days

---

## 📝 DOCTRINE

### Thin Client Principle
GTK app calls ONE endpoint. roxy-core handles all complexity.

### Single Authority
One canonical event stream. One source of truth (Postgres).

### Deterministic Dispatch
Every action is logged. Every automation has audit trail.

### Human-in-the-Loop Default
"Roxy Draft" mode is default. "Roxy Send" requires explicit arming per-thread.

### Progressive Disclosure
- **Now**: Requires immediate reply
- **Queued**: Can wait, but needs response
- **FYI**: No reply needed, informational

### Identity Separation
- Personal life stays personal
- Business/brand has separate channels
- Never mix sender identities

---

## 🎯 IMMEDIATE NEXT ACTIONS

### Lock In Your Top 5 Sources

Reply with your prioritized list. Suggested default:

1. **Email** (personal + business) - fast win
2. **GitHub** (issues/PRs/mentions) - high value, already integrated
3. **Discord** (DMs/mentions) - community active
4. **YouTube comments** - monetization loop
5. **Ops alerts** (Grafana → FYI with escalation)

### Start Phase 1

Once sources confirmed, next session:
1. Add Roxy Chat pane (center column)
2. Add Progressions panel (right column)
3. Add Inbox stub (left column)
4. Wire dispatch button to orchestrator

---

*This plan is the single source of truth for Command Center development.*
*Updated: 2026-01-09 with Chief's Master Architecture*
