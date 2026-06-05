# ROXY Command Center Observe Decision

Status: GREEN review-only observer build.

This pass exposes ROXY quiet-state health inside the Command Center without promoting it to production authority.

Current behavior:

- foreground/manual launch only
- one manual status snapshot at startup
- no background polling daemon
- no autostart
- no systemd unit install
- no model pull
- no disk write/repair/mount/format controls
- no service start/stop/restart controls
- no sleep/suspend controls

Current runtime target:

- Samsung `ROXY_ROOT` mounted at `/`
- SanDisk `ROXY_WORK` mounted at `/mnt/work`
- `ollama.service` on `127.0.0.1:11434`
- `tinyllama:latest` only
- Docker rooted at `/mnt/work/containers/docker`
- `roxy-law0` and `roxy-external-guard`
- `ROXY_SAFETY` blocked and expected unmounted

The observer dashboard is intentionally a glass panel, not a steering wheel. Future production control must go through a separate policy-gated local API and a separate approval ticket.
