# FINAL-WIRING-PLAN.md
## Roxy Command Center ↔ MindSong Orchestrator Integration
**Version**: 1.0
**Date**: 2026-01-09
**Status**: PROPOSED

---

## Executive Summary

This plan defines a clean, auditable architecture for Command Center → Orchestrator integration. The key principle is:

> **Command Center calls ONE audited roxy-core endpoint; roxy-core triggers orchestrator; status streams back; no parallel execution logic.**

---

## 1. PROPOSED ARCHITECTURE

```
┌───────────────────────────────────────────────────────────────┐
│          ROXY COMMAND CENTER (GTK4)                           │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ Services     │  │ Ollama       │  │ Orchestrator Panel   │ │
│  │ Page         │  │ Panel        │  │ (NEW)                │ │
│  └──────────────┘  └──────────────┘  └───────────┬──────────┘ │
│                                                   │            │
│                          Single HTTP call         │            │
└──────────────────────────────────────────────────┼────────────┘
                                                    │
                                                    ▼
┌───────────────────────────────────────────────────────────────┐
│                    ROXY CORE API                               │
│                    (localhost:8000)                            │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ POST /api/orchestrator/dispatch                         │   │
│  │   - Validates request                                   │   │
│  │   - Logs to audit trail                                 │   │
│  │   - Forwards to Podium                                  │   │
│  │   - Returns job_id for tracking                         │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ GET /api/orchestrator/status/{job_id}                   │   │
│  │ WebSocket /api/orchestrator/stream                      │   │
│  │   - Real-time status updates                            │   │
│  │   - Proxies Podium telemetry                            │   │
│  └────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────┬───────────┘
                                                    │
                                                    ▼
┌───────────────────────────────────────────────────────────────┐
│                    LUNO ORCHESTRATOR                           │
│                    (localhost:3847)                            │
│                                                                │
│  Podium Server → Conductor → Enqueue Kernel → Agents          │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

---

## 2. SINGLE DISPATCH ENDPOINT

### Endpoint: `POST /api/orchestrator/dispatch`

**Request**:
```json
{
  "action": "enqueue_story" | "enqueue_plan" | "halt" | "status",
  "payload": {
    "story_id": "STORY-001",        // for enqueue_story
    "plan_id": "SKOREQ-XXX",        // for enqueue_plan
    "nonce": "xxx"                  // for apply operations
  },
  "source": "command-center",
  "auth": {
    "user_id": "mark",
    "session_id": "xxx"
  }
}
```

**Response**:
```json
{
  "success": true,
  "job_id": "JOB-20260109-001",
  "status": "queued",
  "audit_id": "AUD-xxx",
  "stream_url": "ws://localhost:8000/api/orchestrator/stream/JOB-20260109-001"
}
```

### Audit Log Entry
Every dispatch logs to `~/.roxy/logs/orchestrator-audit.jsonl`:
```json
{
  "timestamp": "2026-01-09T08:00:00Z",
  "audit_id": "AUD-xxx",
  "action": "enqueue_story",
  "story_id": "STORY-001",
  "source": "command-center",
  "user_id": "mark",
  "result": "queued",
  "podium_response": {...}
}
```

---

## 3. PROGRESSIONS PLAY BUTTON FLOW

### Current Flow (MindSong Frontend)
```
DispatchButton.tsx → useOrchestratorCommands → WebSocket :3847 → Podium
```

### New Flow (Command Center)
```
OrchestratorPanel.py → HTTP POST /api/orchestrator/dispatch → roxy_core.py 
                     → Forward to Podium :3847
                     → Stream status back via WebSocket
```

### Code Changes Required

#### A. roxy_core.py - Add Orchestrator Proxy
```python
# New route in roxy_core.py

@app.post("/api/orchestrator/dispatch")
async def orchestrator_dispatch(request: OrchestratorRequest):
    """Single dispatch endpoint - all orchestrator commands go here."""
    
    # 1. Validate
    if not request.action in ALLOWED_ACTIONS:
        raise HTTPException(400, "Invalid action")
    
    # 2. Audit log
    audit_id = log_orchestrator_action(request)
    
    # 3. Forward to Podium
    async with aiohttp.ClientSession() as session:
        podium_url = f"http://localhost:3847/api/command"
        async with session.post(podium_url, json={
            "type": action_to_podium_type(request.action),
            **request.payload
        }) as resp:
            result = await resp.json()
    
    # 4. Return with tracking
    return {
        "success": True,
        "job_id": generate_job_id(),
        "audit_id": audit_id,
        "podium_result": result
    }
```

#### B. Command Center - OrchestratorPanel
```python
# New widget: widgets/orchestrator_panel.py

class OrchestratorPanel(Gtk.Box):
    """Orchestrator control panel for Command Center."""
    
    def dispatch_story(self, story_id: str):
        """Dispatch a single story."""
        response = requests.post(
            "http://localhost:8000/api/orchestrator/dispatch",
            json={
                "action": "enqueue_story",
                "payload": {"story_id": story_id},
                "source": "command-center"
            }
        )
        return response.json()
    
    def get_queue_status(self):
        """Get current queue status."""
        response = requests.get(
            "http://localhost:8000/api/orchestrator/status"
        )
        return response.json()
```

---

## 4. STATUS STREAMING

### WebSocket Endpoint: `/api/orchestrator/stream`

```python
@app.websocket("/api/orchestrator/stream")
async def orchestrator_stream(websocket: WebSocket):
    """Stream orchestrator status updates."""
    await websocket.accept()
    
    # Connect to Podium WebSocket
    async with websockets.connect("ws://localhost:3847/ws") as podium_ws:
        async for message in podium_ws:
            data = json.loads(message)
            
            # Filter and forward relevant updates
            if data.get("type") in ["QUEUE_UPDATE", "STORY_STATUS", "AGENT_STATUS"]:
                await websocket.send_json(data)
```

### Command Center Integration
```python
# In main.py - connect to status stream

def _connect_orchestrator_stream(self):
    """Connect to orchestrator status stream."""
    import websocket
    
    def on_message(ws, message):
        data = json.loads(message)
        GLib.idle_add(self._update_orchestrator_status, data)
    
    ws = websocket.WebSocketApp(
        "ws://localhost:8000/api/orchestrator/stream",
        on_message=on_message
    )
    threading.Thread(target=ws.run_forever, daemon=True).start()
```

---

## 5. NO PARALLEL EXECUTION LOGIC

### Key Invariants

1. **Single Entry Point**: All orchestrator commands go through `/api/orchestrator/dispatch`
2. **No Direct Podium Access**: Command Center never talks to :3847 directly
3. **Audit First**: Every action logged before execution
4. **Sequential Processing**: One story at a time (unless Podium handles batching)
5. **Status Passthrough**: roxy-core only proxies, doesn't interpret

### What Command Center Does NOT Do
- ❌ Parse SKOREQ plans
- ❌ Validate story eligibility
- ❌ Manage agent pool
- ❌ Handle execution errors (just displays them)
- ❌ Store queue state (stateless UI)

### What roxy-core Does
- ✅ Single dispatch endpoint
- ✅ Audit logging
- ✅ Auth validation
- ✅ Forward to Podium
- ✅ Stream status back
- ✅ Rate limiting (optional)

---

## 6. IMPLEMENTATION PHASES

### Phase 1: Endpoint Scaffolding (2 hours)
- [ ] Add `/api/orchestrator/dispatch` to roxy_core.py
- [ ] Add `/api/orchestrator/status` to roxy_core.py
- [ ] Add audit logging to ~/.roxy/logs/

### Phase 2: Command Center Panel (4 hours)
- [ ] Create `widgets/orchestrator_panel.py`
- [ ] Add to navigation as "Orchestrator" page
- [ ] Wire dispatch button
- [ ] Wire status display

### Phase 3: Status Streaming (2 hours)
- [ ] Add WebSocket proxy endpoint
- [ ] Connect Command Center to stream
- [ ] Display real-time queue status

### Phase 4: Testing & Polish (2 hours)
- [ ] End-to-end dispatch test
- [ ] Audit log verification
- [ ] Error handling
- [ ] UI polish

**Total Estimate**: 10 hours

---

## 7. SECURITY CONSIDERATIONS

### Auth Flow
```
Command Center → roxy-core (local, no auth needed)
roxy-core → Podium (uses PODIUM_JWT_SECRET if set)
```

### Rate Limiting
```python
# In roxy_core.py
DISPATCH_RATE_LIMIT = 10  # per minute
DISPATCH_COOLDOWN = 5     # seconds between same-story dispatches
```

### Audit Retention
- Keep audit logs for 90 days minimum
- Rotate daily
- Include hash chain for tamper detection (like immutable-log.ts)

---

## 8. SUCCESS CRITERIA

1. ✅ Can dispatch a story from Command Center
2. ✅ Dispatch appears in audit log
3. ✅ Podium receives the command
4. ✅ Status streams back to Command Center
5. ✅ No duplicate executions
6. ✅ Errors displayed clearly
7. ✅ Works with SKOREQ plans

---

## APPENDIX: Current Port Map

| Port | Service | Role |
|------|---------|------|
| 8000 | roxy-core | **Single entry point** |
| 3847 | Podium | Orchestrator (internal) |
| 4899 | Gateway | Voice commands (parallel path) |
| 11434 | Ollama BIG | Model serving |
| 11435 | Ollama FAST | Model serving |

The Command Center only talks to **8000**. Everything else is internal.
