# WIRING-AUDIT.md
## ROXY ↔ MindSong Orchestrator Deep Archaeology Report
**Generated**: 2026-01-09
**Scope**: mindsong-juke-hub, .roxy, luno-orchestrator

---

## 1. ORCHESTRATOR ENDPOINTS

### LUNO Podium Server (Port 3847)
**Location**: `luno-orchestrator/src/podium/server.ts`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ws` | WebSocket | Real-time telemetry + command dispatch |
| `/health` | GET | System health check |
| `/api/status` | GET | Orchestrator status |
| `/api/command` | POST | Send orchestrator commands |
| `/api/governance/skoreq/prepare-apply` | POST | Stage SKOREQ plan |
| `/api/governance/skoreq/apply` | POST | Apply plan with nonce |
| `/api/governance/skoreq/enqueue` | POST | Enqueue stories from plan |

### ROXY Command Gateway (Port 4899)
**Location**: `luno-orchestrator/src/roxy/roxy-command-gateway.ts`

Supported Intents:
```typescript
type RoxyIntent =
  | 'status'           // Get orchestrator status
  | 'prepare_apply'    // Stage SKOREQ plan
  | 'apply_plan'       // Apply staged plan
  | 'enqueue_plan'     // Queue entire plan
  | 'enqueue_story'    // Queue single story
  | 'halt'             // Emergency stop
  | 'set_limits';      // Configure limits
```

### MCP Orchestrator Bridge
**Location**: `~/.roxy/mcp/mcp_orchestrator.py`

```python
LUNO_API_BASE = "http://localhost:3000"  # Legacy?
LUNO_PODIUM_WS = "ws://localhost:3847"

TOOLS = {
    "orchestrator_create_task",
    "orchestrator_get_status",
    "orchestrator_dispatch_to_citadel",
    "orchestrator_cancel_task",
    "orchestrator_list_tasks",
    "citadel_health_check"
}
```

---

## 2. AUTHENTICATION

### Podium Auth System
**Location**: `luno-orchestrator/src/podium/auth.ts`

```typescript
// JWT-based auth
export type AuthRole = 'admin' | 'viewer';

// Production requires PODIUM_JWT_SECRET
// Development allows auth bypass

// WebSocket auth:
wsUrl.searchParams.set('token', authToken);

// HTTP auth:
headers: { 'Authorization': `Bearer ${token}` }
```

### Gateway Token (Separate!)
**Location**: Frontend `.env`

```bash
VITE_ROXY_GATEWAY_TOKEN=xxx  # Different from Podium token!
```

### Auth Context for Enqueue
```typescript
interface AuthContext {
  userId?: string;
  isAdmin: boolean;
  authMode?: 'authenticated' | 'dev-bypass';
}
```

⚠️ **ISSUE**: Gateway token ≠ Podium token - no unified auth

---

## 3. ACTION BROKER / AUDIT EXECUTOR

### Enqueue Kernel (SINGLE SOURCE OF TRUTH)
**Location**: `luno-orchestrator/src/orchestrator/enqueue-kernel.ts`

**Invariants Enforced**:
1. Single enqueue path (WS and HTTP both route here)
2. Atomic queue writes (temp file → rename)
3. Dispatch readiness gate
4. Story eligibility validation
5. Audit logging REQUIRED

```typescript
const ENQUEUEABLE_STATUSES = ['todo', 'pending', 'queued', 'blocked'];
const BLOCKED_STATUSES = ['done', 'cancelled', 'in_progress'];

// Every enqueue logs:
writeAuditLog({
  timestamp, action: 'enqueue',
  storyId, source, tier, userId, authMode, requestPath
});
```

### Immutable Audit Log
**Location**: `luno-orchestrator/src/audit/immutable-log.ts`

- Hash chain for tamper detection
- Append-only structure  
- Cryptographic signatures (optional)
- Log rotation support

```typescript
export type AuditEventType =
  | 'commit.created' | 'commit.reverted'
  | 'branch.created' | 'branch.merged'
  | 'pr.opened' | 'pr.merged'
  | 'rollback.executed'
  | 'scope.violation';
```

### Queue Logger (SQLite)
**Location**: `luno-orchestrator/src/orchestrator/queue-logger.ts`

`task_audit` table for local audit trail.

---

## 4. PROGRESSIONS PLAY BUTTONS

### Dispatch Button Component
**Location**: `mindsong-juke-hub/src/components/mosProgressions/DispatchButton.tsx`

```tsx
import { Play, Loader2 } from 'lucide-react';

// Sends via WebSocket:
const result = await sendCommand({
  type: 'ENQUEUE_STORY',
  storyId: orchestratorStoryId
});

// Telemetry:
window.telemetry.track('dispatch_requested', {
  lunoId, orchId: orchestratorStoryId, mode: 'single'
});
```

### ROXY Execution Panel
**Location**: `mindsong-juke-hub/src/components/mosProgressions/RoxyExecutionPanel.tsx`

Two-step governance buttons:
```tsx
// SKOREQ Plan Flow:
handlePrepareApply → handleApplyConfirm

// Enqueue Flow:
handleEnqueueStage → handleEnqueueConfirm

// Single Story:
handleEnqueueStoryStage → handleEnqueueStoryConfirm

// Bulk Stories:
handleStageSelectedStories → handleConfirmSelectedStories
```

### Frontend Hooks
- `src/hooks/useOrchestratorCommands.ts` - WebSocket command sending
- `src/hooks/usePodiumConnection.ts` - Real-time telemetry stream

---

## 5. GIT HISTORY - KEY WIRING COMMITS

### mindsong-juke-hub
```
df6182180e WIP: metronome convergence, LUNO updates, ROXY setup (92 files)
4f220d64fd chore(scripts): archive luno-migration scripts
f09416ce32 governance(progress): apply SKOREQ plan NVX1-METRONOME-CONVERGENCE-V1
0625233dc2 Agent breakroom skills, MOS cockpit updates
46844cf5f0 feat(roxy-monitor): STORY-002 - /status endpoint patch
eedd4c9e2d governance(progress): apply SKOREQ plan ROXY-MONITOR-TUI-V1
```

### .roxy
```
aa16820 Add Roxy Command Center GTK4 application
e5a62ce feat: Apollo bridge MCP wiring + dual wake-word persona routing
448a3b1 🚀 Sprint 2 Apollo Audio Bridge + MCP Music Tools
054dbe0 🤖 Hardware automation suite: GPU monitor, power profiles, OBS
```

---

## 6. WHAT EXISTS vs WHAT'S MISSING

### ✅ FULLY WIRED
| Component | Location | Evidence |
|-----------|----------|----------|
| Podium WebSocket | :3847/ws | Telemetry streaming works |
| SKOREQ governance | /api/governance/* | prepare-apply, apply, enqueue |
| Enqueue kernel | enqueue-kernel.ts | Unified dispatch |
| Audit logging | immutable-log.ts | JSONL + SQLite |
| Dispatch buttons | DispatchButton.tsx | Play ▶️ icon |
| Auth tokens | auth.ts | JWT + Bearer |
| MCP bridge | mcp_orchestrator.py | Tools exposed |
| Telemetry hooks | usePodiumConnection.ts | React hooks |

### ⚠️ INCOMPLETE
| Component | Issue |
|-----------|-------|
| Gateway↔Podium | Separate services, not unified |
| Citadel dispatch | Depends on 10.0.0.65 being online |
| LUNO port 3000 | Referenced but may be legacy |
| Hub location | Moved to Mac Studio (10.0.0.92) |

### ❌ MISSING
| Component | Impact |
|-----------|--------|
| /progressions route | No frontend route found |
| Auto-play batch | Disabled by `ENABLE_AUTO_DISPATCH=false` |
| Cross-service auth sync | Gateway ≠ Podium tokens |
| Status streaming to Command Center | Not wired |

---

## 7. PORT MAP

| Port | Service | Protocol |
|------|---------|----------|
| 3000 | LUNO API (legacy?) | HTTP |
| 3847 | Podium Server | HTTP + WS |
| 4899 | ROXY Command Gateway | HTTP |
| 8765 | Citadel Health | HTTP |
| 8766 | Citadel Control | HTTP |
| 11434 | Ollama W5700X | HTTP (accepts BIG alias) |
| 11435 | Ollama 6900XT | HTTP (accepts FAST alias) |

---

## 8. ARCHITECTURE SUMMARY

```
┌──────────────────────────────────────────────────────────────┐
│              MINDSONG JUKE HUB (Frontend)                    │
│  RoxyExecutionPanel.tsx ─┬─ DispatchButton.tsx (Play ▶️)     │
│                          │                                    │
│  useOrchestratorCommands.ts / usePodiumConnection.ts         │
│  WebSocket: ws://localhost:3847/ws                           │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│              LUNO ORCHESTRATOR                               │
│  Podium Server :3847 ──► Conductor ──► Enqueue Kernel        │
│  (WS + HTTP)              (5s beat)    (Audit + Dispatch)    │
└────────────────────────────┬─────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ ROXY (.roxy/)   │  │ Citadel Worker  │  │ Agent Pool      │
│ MCP Bridge      │  │ 10.0.0.65       │  │ (Friday, etc)   │
│ Command Gateway │  │ :8765/:8766     │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```
