# Friday Profile Receipt

Date: 2026-06-12
Repo: roxy-command-center
Purpose: Add read-only Friday / citadel-worker-1 profile scaffolding.

## Changes

```text
profiles/friday.json
services/profile_config.py
services/friday_status_provider.py
services/rcc_command_kernel_adapter.py
scripts/install-friday-profile.sh
docs/FRIDAY_PROFILE.md
docs/FRIDAY_PROFILE_RECEIPT_20260612.md
```

Also fixed:

```text
services/operator_kernel_client.py
```

The Operator Kernel client now imports `datetime` at module scope so
`build_action_packet("kernel.state.get")` can run outside the `__main__` smoke
path.

## Authority Proof

```text
native GTK4 app source: roxy-command-center
RCC command kernel: mindsong-juke-hub/scripts/rcc/rcc.mjs
Friday profile: sourceAuthority=false
```

Friday profile disables the Terminal page and raw shell route. It also disables
Ollama and voice/action mutation pages. Service start/stop/restart remains
blocked by the existing read-only service controls.

## Validation Commands

```bash
python3 -m py_compile $(find . -name '*.py' -not -path './.git/*')
desktop-file-validate roxy-command-center.desktop
bash -n scripts/install-friday-profile.sh
python3 - <<'PY'
from services.profile_config import load_profile
p = load_profile("friday")
assert p["sourceAuthority"] is False
assert "terminal" in p["disabledPages"]
print("PROFILE_OK")
PY
python3 - <<'PY'
from services.operator_kernel_client import build_action_packet
pkt = build_action_packet("kernel.state.get")
assert pkt["action"] == "kernel.state.get"
assert pkt["actionType"] == "kernel.state.get"
assert "id" in pkt
assert "actionId" in pkt
assert "requestedAt" in pkt
assert "timestamp" in pkt
print("ACTION_PACKET_OK")
PY
python3 - <<'PY'
from services.rcc_command_kernel_adapter import is_allowed_command
assert is_allowed_command("roxy.status")
assert not is_allowed_command("arbitrary-shell")
print("RCC_ADAPTER_POLICY_OK")
PY
git diff --check
```

Actual validation on Friday:

```text
python3 -m py_compile: PASS
desktop-file-validate roxy-command-center.desktop: PASS with existing category hint
bash -n scripts/install-friday-profile.sh: PASS
python3 scripts/smoke-friday-profile.py: PASS
services.friday_status_provider smoke: PASS (fresh, citadel-worker-1, headMatch True)
services.rcc_command_kernel_adapter smoke: PASS (roxy.status delegated; arbitrary-shell denied)
RCC_PROFILE=friday import main: PASS
git diff --check: PASS
shellcheck: not installed on Friday
```

`roxy.status` currently returns the command kernel's structured `FAIL` verdict
with exit code 1 on Friday because Roxy service truth is red from that view. The
adapter preserves that truth and still proves delegation plus policy rejection.

## Not Included

- No package installation.
- No sudo.
- No service mutation.
- No migration of native RCC source into `mindsong-juke-hub`.
- No new Bridge, Podium, command registry, action gateway, or receipt authority.
