#!/usr/bin/env python3
"""
Receipts / Proof Page — Audit trail and proof debt.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any
import json
from pathlib import Path


class ReceiptsProofPage(Gtk.ScrolledWindow):
    """Audit trail and proof debt visibility."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        title = Gtk.Label(label="Receipts & Proof")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        # Proof debt summary
        self.debt_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.debt_box.set_margin_bottom(16)
        main_box.append(self.debt_box)

        # Judge status
        self.judge_label = Gtk.Label(label="")
        self.judge_label.add_css_class("caption")
        self.judge_label.set_xalign(0)
        main_box.append(self.judge_label)

        # Recent receipts
        receipts_title = Gtk.Label(label="Recent Receipts")
        receipts_title.add_css_class("title-3")
        receipts_title.set_xalign(0)
        main_box.append(receipts_title)

        self.receipts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        main_box.append(self.receipts_box)

    def _read_proof_debt(self) -> dict:
        try:
            path = Path("/mnt/work/ssot/mindsong-juke-hub/output/regent/judge-reports/proof-debt-ledger.json")
            if path.exists():
                with open(path) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _read_receipts(self) -> list:
        receipts = []
        try:
            path = Path("/mnt/work/ssot/mindsong-juke-hub/output/regent/action-receipts.ndjson")
            if path.exists():
                lines = path.read_text().strip().splitlines()
                for line in lines[-15:]:
                    try:
                        receipts.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass

        # Also read RCC receipts
        try:
            rcc_root = Path("/mnt/work/ssot/mindsong-juke-hub/output/rcc/receipts")
            if rcc_root.exists():
                for cmd_dir in rcc_root.iterdir():
                    if not cmd_dir.is_dir():
                        continue
                    files = sorted(cmd_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
                    for f in files:
                        try:
                            data = json.loads(f.read_text())
                            receipts.append({
                                "schemaVersion": "rcc-receipt.v1",
                                "action": data.get("commandId", "unknown"),
                                "source": "rcc-command-kernel",
                                "requestedAt": data.get("finishedAt", ""),
                                "status": data.get("result", {}).get("verdict", "unknown").lower(),
                                "receiptPath": str(f),
                                "payload": data.get("result", {}),
                            })
                        except Exception:
                            pass
        except Exception:
            pass

        # Sort by time, newest first
        receipts.sort(key=lambda r: r.get("requestedAt", ""), reverse=True)
        return receipts[:30]

    def update(self, data: dict):
        # Proof debt
        while self.debt_box.get_first_child():
            self.debt_box.remove(self.debt_box.get_first_child())

        debt = self._read_proof_debt()
        ledger = debt.get("ledger", [])

        debt_title = Gtk.Label(label=f"Proof Debt: {len(ledger)} entries")
        debt_title.add_css_class("title-3")
        debt_title.set_xalign(0)
        self.debt_box.append(debt_title)

        for entry in ledger[:5]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            eid = Gtk.Label(label=entry.get("entryId", "?"))
            eid.set_size_request(80, -1)
            eid.add_css_class("monospace-small")

            claim = Gtk.Label(label=entry.get("claim", "")[:50])
            claim.set_hexpand(True)
            claim.set_xalign(0)
            claim.set_wrap(True)

            src = Gtk.Label(label=entry.get("sourceAgent", "?"))
            src.add_css_class("caption")
            src.set_xalign(1)

            row.append(eid)
            row.append(claim)
            row.append(src)
            self.debt_box.append(row)

        # Judge status
        judge = data.get("judgeAuthority", {})
        verdict = judge.get("verdict", "?")
        brief = "yes" if judge.get("briefPipelineRan") else "no"
        self.judge_label.set_label(f"Judge: {verdict} · Brief pipeline: {brief}")

        # Receipts
        while self.receipts_box.get_first_child():
            self.receipts_box.remove(self.receipts_box.get_first_child())

        receipts = self._read_receipts()
        for r in receipts:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            ts = r.get("ts", "")[:19]
            verb = r.get("verb", "?")
            exit_code = r.get("exit", 0)
            text = f"{'✓' if exit_code == 0 else '✗'} {ts} · {verb}"
            lbl = Gtk.Label(label=text)
            lbl.add_css_class("monospace-small")
            lbl.set_xalign(0)
            if exit_code != 0:
                lbl.add_css_class("status-blocked-text")
            row.append(lbl)
            self.receipts_box.append(row)
