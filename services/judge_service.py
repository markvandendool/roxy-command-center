#!/usr/bin/env python3
"""
Judge Service — Async adversarial review with job queue.

Creates background jobs for Judge (235B CPU) calls so the GTK UI never freezes.
Jobs are written to runtime/judge/jobs/ and output/judge/receipts/.
"""

import json
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Callable

from services.action_receipt_service import write_action_receipt, update_receipt_status

JOB_DIR = Path(__file__).parent.parent / "runtime" / "judge" / "jobs"
RECEIPT_DIR = Path(__file__).parent.parent / "output" / "judge" / "receipts"

ROXY_CHAT_PROXY_URL = "http://127.0.0.1:4001"


def _ensure_dirs():
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return datetime.now().isoformat()


class JudgeJob:
    """A single Judge review job."""

    def __init__(self, job_id: str, prompt: str, context: str, source_mission_id: str):
        self.job_id = job_id
        self.prompt = prompt
        self.context = context
        self.source_mission_id = source_mission_id
        self.status = "queued"  # queued | running | completed | failed | timeout
        self.result = ""
        self.error = ""
        self.created_at = _ts()
        self.completed_at = ""
        self.receipt_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jobId": self.job_id,
            "status": self.status,
            "prompt": self.prompt,
            "context": self.context,
            "sourceMissionId": self.source_mission_id,
            "result": self.result,
            "error": self.error,
            "createdAt": self.created_at,
            "completedAt": self.completed_at,
        }

    def save(self):
        path = JOB_DIR / f"{self.job_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8")


class JudgeService:
    """Background Judge review service."""

    def __init__(self):
        _ensure_dirs()
        self._jobs: Dict[str, JudgeJob] = {}
        self._callbacks: Dict[str, Callable[[JudgeJob], None]] = {}
        self._load_existing_jobs()

    def _load_existing_jobs(self):
        """Load existing job files from disk."""
        for f in JOB_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                job = JudgeJob(
                    data["jobId"],
                    data.get("prompt", ""),
                    data.get("context", ""),
                    data.get("sourceMissionId", ""),
                )
                job.status = data.get("status", "queued")
                job.result = data.get("result", "")
                job.error = data.get("error", "")
                job.created_at = data.get("createdAt", "")
                job.completed_at = data.get("completedAt", "")
                self._jobs[job.job_id] = job
            except Exception:
                pass

    def submit_job(
        self,
        prompt: str,
        context: str = "",
        source_mission_id: str = "",
        on_complete: Optional[Callable[[JudgeJob], None]] = None,
    ) -> JudgeJob:
        """Submit a new Judge review job."""
        job_id = f"judge-{uuid.uuid4().hex[:12]}"
        job = JudgeJob(job_id, prompt, context, source_mission_id)
        job.status = "queued"
        job.save()
        self._jobs[job_id] = job

        # Write action receipt
        receipt_path = write_action_receipt(
            action="judge",
            mission_id=source_mission_id or "chat",
            mission_title=context[:60] or "Judge Review",
            status="queued",
            target_agent="roxy-judge",
            target_lane="judge",
            authority="operator",
            payload={"jobId": job_id, "promptPreview": prompt[:200]},
            next_action="polling for completion",
        )
        job.receipt_path = receipt_path
        job.save()

        if on_complete:
            self._callbacks[job_id] = on_complete

        # Start background thread
        thread = threading.Thread(target=self._run_job, args=(job,), daemon=True)
        thread.start()

        print(f"[JudgeService] Job {job_id} queued")
        return job

    def _run_job(self, job: JudgeJob):
        """Background thread: call Judge and update job."""
        job.status = "running"
        job.save()
        if job.receipt_path:
            update_receipt_status(job.receipt_path, "pending")

        try:
            import urllib.request
            import urllib.error

            payload = {
                "model": "roxy-cpu-supermodel",
                "messages": [
                    {"role": "system", "content": "You are ROXY Judge, an adversarial reviewer. Be concise and critical."},
                    {"role": "user", "content": job.prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 1024,
            }

            req = urllib.request.Request(
                f"{ROXY_CHAT_PROXY_URL}/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            # 180s timeout for Judge
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    job.result = content
                    job.status = "completed"
                else:
                    job.status = "failed"
                    job.error = "No choices in response"

        except urllib.error.HTTPError as e:
            job.status = "failed"
            job.error = f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            job.status = "failed"
            job.error = str(e)

        job.completed_at = _ts()
        job.save()

        # Update receipt
        if job.receipt_path:
            update_receipt_status(
                job.receipt_path,
                job.status,
                payload={"resultPreview": job.result[:200], "completedAt": job.completed_at},
                error=job.error,
            )

        # Callback
        callback = self._callbacks.pop(job.job_id, None)
        if callback:
            try:
                callback(job)
            except Exception as e:
                print(f"[JudgeService] Callback error: {e}")

        print(f"[JudgeService] Job {job.job_id} -> {job.status}")

    def get_job(self, job_id: str) -> Optional[JudgeJob]:
        """Get a job by ID."""
        job = self._jobs.get(job_id)
        if job:
            # Refresh from disk
            path = JOB_DIR / f"{job_id}.json"
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    job.status = data.get("status", job.status)
                    job.result = data.get("result", job.result)
                    job.error = data.get("error", job.error)
                    job.completed_at = data.get("completedAt", job.completed_at)
                except Exception:
                    pass
        return job

    def list_jobs(self, limit: int = 20) -> list:
        """List recent jobs, newest first."""
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs[:limit]]

    def get_pending_jobs(self) -> list:
        """Get jobs that are queued or running."""
        return [j.to_dict() for j in self._jobs.values() if j.status in ("queued", "running")]


# Singleton
_judge_service: Optional[JudgeService] = None


def get_judge_service() -> JudgeService:
    global _judge_service
    if _judge_service is None:
        _judge_service = JudgeService()
    return _judge_service
