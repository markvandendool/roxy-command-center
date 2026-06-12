# Friday Profile

Friday / `citadel-worker-1` is a read-only native RCC cockpit target for the
MindSong/Roxy system.

## Source Boundary

```text
roxy-command-center
  native GTK4/libadwaita RCC app source

mindsong-juke-hub/scripts/rcc/rcc.mjs
  RCC command kernel, receipts, Operator Kernel state

Friday ~/.local/lib/mindsong-rcc
  deployed proof/profile, sourceAuthority=false
```

Do not move native RCC source into `mindsong-juke-hub` without a governed
SKOREQ. Do not make Friday a source authority.

## Running

```bash
RCC_PROFILE=friday python3 main.py
```

or after installation:

```bash
scripts/install-friday-profile.sh
rcc-roxy-command-center
```

## Profile Behavior

The Friday profile is loaded from `profiles/friday.json` via `RCC_PROFILE=friday`.

It exposes only read-oriented pages:

```text
overview
receipts
services
roxy_status
mos_cockpit
alerts
```

It disables pages that can mutate state or expose raw execution:

```text
terminal
ollama
voice_actions
agents
orchestrator
home/chat
```

The header shows `FRIDAY READ-ONLY | sourceAuthority=false` so the operator can
see the authority mode at runtime.

## Status Provider

`services/friday_status_provider.py` invokes the configured `statusCommand`
(`/home/mark/bin/rcc-status` by default) with a bounded timeout, parses JSON,
redacts secret-like keys, and reports:

- host
- generatedAt
- disk
- failed unit count
- bridge headMatch and heads
- local service states
- operator health
- freshness: `fresh`, `stale`, or `unknown`
- `sourceAuthority=false`

The status provider does not treat local cached JSON as sole truth. If bridge
heads differ from a live Bridge check, the UI/report must label freshness rather
than pretending cached state is authoritative.

## Command Kernel Adapter

`services/rcc_command_kernel_adapter.py` delegates to the existing command
kernel:

```text
node /home/mark/mindsong-juke-hub/scripts/rcc/rcc.mjs <command> --json
```

It does not use `shell=True`, does not accept arbitrary shell input, and allows
only commands listed in the active profile.

## Forbidden In Friday Profile

```text
arbitrary_shell
service_restart
service_stop
service_start
git_commit
git_push
source_write
secret_read
```
