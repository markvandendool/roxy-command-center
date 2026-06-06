# ROXY Command Center Adapt Decision

Date: 2026-05-06 12:45:38 America/Edmonton

## Decision

The preserved ROXY Command Center has been adapted into a current-runtime,
review-only build:

```text
/mnt/work/roxy-core/apps/roxy-command-center-current-roxy-adapt
```

This build is allowed for foreground review. It is not installed as production
authority, does not install systemd units, does not autostart, and does not create
or assume `roxy-core.service`.

## Current Runtime Mapping

The adapted app now targets the real current ROXY runtime:

```text
Ollama service:
  unit: ollama.service
  API: http://127.0.0.1:11434
  models path: /mnt/work/ollama
  current model: tinyllama:latest

Storage:
  /: Samsung ROXY_ROOT
  /mnt/work: SanDisk ROXY_WORK

Safety:
  roxy-law0 required
  roxy-external-guard required
  ROXY_SAFETY must remain unmounted
```

Removed from active Python/launcher code:

```text
ollama-6900xt.service
ollama-big.service
ollama-fast.service
port 11435 active control
roxy-core.service active control
systemctl suspend path
destructive disk command references
```

Historical planning documents remain in the tree as reference material and still
describe future roxy-core / dual-pool ideas. They are not active runtime code.

## Safety Posture

Service cards are read-only in this build. Start, stop, and restart controls are
disabled and show a read-only notice if clicked.

The header sleep button is disabled and shows a read-only notice.

ChatService now talks directly to local Ollama using `/api/tags` and
`/api/generate`. It does not require a production `roxy-core` service.

## Validation

Evidence directory:

```text
/mnt/work/roxy-core/apps/roxy-command-center-adapt-evidence-20260506_124538
```

Static validation:

```text
Python syntax: PASS
files checked: 26
active stale/destructive scan: clean
runtime dependency check: PASS
```

Runtime dependency check confirmed:

```text
Python 3.12: OK
GTK4 / Libadwaita / Soup: OK
Ollama API 127.0.0.1:11434: OK
tinyllama:latest present: OK
roxy-law0: PASS
roxy-external-guard: PASS
/mnt/work mounted: OK
Docker root: /mnt/work/containers/docker
ROXY_SAFETY not mounted: OK
```

Foreground smoke:

```text
/mnt/work/roxy-core/apps/roxy-command-center-adapt-smoke-20260506_124538
```

Result:

```text
GTK app started
main window created
UI presented on X11
Ollama connected at http://127.0.0.1:11434
1 model visible
terminated by intentional timeout
no install
no autostart
no service creation
```

Exit code `124` is expected because the smoke test used `timeout 8s` to stop the
foreground app after proving startup and connection.

## Known Remaining Work

This is now a good review build, not a production control authority.

Next refinements should be UI polish and controlled feature work:

```text
1. Replace old placeholder inbox/run mocks with current ROXY status cards.
2. Add explicit Law 0 / external guard status widgets.
3. Add a non-mutating storage status panel for Samsung, SanDisk, P51, and blocked ROXY_SAFETY.
4. Add a tinyllama chat smoke button that clearly says it uses local Ollama only.
5. Keep service mutation disabled until a separate production-control ticket exists.
6. Keep future roxy-core / dual-Ollama plans documented but inactive.
```

## Final Classification

```text
ROXY-COMMAND-CENTER-ADAPT-005:
  status: GREEN review build
  production installed: no
  foreground smoke: pass
  active dual-Ollama references: none
  active roxy-core.service references: none
  service mutation: disabled
  disk mutation: none
  model pulls: none
```
