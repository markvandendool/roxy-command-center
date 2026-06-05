# Historical Docs Are Not Runtime

This tree contains recovered ROXY Command Center planning material from earlier ROXY eras.

Historical files may mention:

- `roxy-core.service`
- port `11435`
- W5700X / 6900XT routing
- BIG / FAST Ollama pools
- `ollama-6900xt.service`
- `ollama-big.service`
- `ollama-fast.service`
- old sleep, service mutation, and orchestration plans

Those references are preserved for design lineage only. They are not current ROXY runtime controls.

The current approved review runtime is:

- one `ollama.service` on `127.0.0.1:11434`
- `tinyllama:latest` as plumbing smoke only
- Samsung `ROXY_ROOT` as `/`
- SanDisk `ROXY_WORK` as `/mnt/work`
- Docker data-root at `/mnt/work/containers/docker`
- `roxy-law0` and `roxy-external-guard` as safety gates
- no service mutation
- no disk mutation
- no sleep/suspend controls
- no production install or autostart

Use `ADAPT_DECISION.md`, `OBSERVE_DECISION.md`, `runtime_check.py`, and `daemon_client.py` for current behavior.
