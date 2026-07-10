#!/usr/bin/env python3
"""Zero-trust contract tests for native RCC -> ROXY harness -> Ada."""

import json
import sys
import time
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.chat_service import (
    ChatService,
    build_harness_payload,
    validate_harness_response,
)
from widgets.home_console_page import ChatMessage, ChatMessage_Widget
from widgets.home_console_page import TalkColumn
from services.chat_service import ConnectionStatus
from datetime import datetime


MODEL = "roxy-coder-frontier"


def valid_response(content="ADA_NATIVE_CONTRACT_OK"):
    return {
        "model": MODEL,
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"total_tokens": 42},
        "timings": {"prompt_ms": 100, "predicted_ms": 200, "predicted_per_second": 25.0},
        "roxy": {
            "sessionId": "roxy_contract_123",
            "persistenceStatus": "live",
            "memoryStatus": "persisted",
            "identityCapsuleApplied": True,
            "harnessEnforced": False,
            "degradedFallback": False,
            "harnessBypassDetected": False,
            "routeDecision": {
                "originalModel": MODEL,
                "selectedModel": MODEL,
                "rerouted": False,
            },
        },
    }


def test_payload_uses_openai_messages_and_session():
    payload = build_harness_payload(
        [{"role": "user", "content": "hello"}],
        MODEL,
        "session-1",
        "CHAT",
    )
    assert payload["model"] == MODEL
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert "prompt" not in payload
    assert payload["session_id"] == "session-1"
    assert payload["roxy_route_mode"] == "CHAT"
    assert payload["chat_template_kwargs"]["enable_thinking"] is False
    assert payload["stream"] is False


def test_valid_route_is_accepted():
    result = validate_harness_response(valid_response(), MODEL)
    assert result["ok"]
    assert result["sessionId"] == "roxy_contract_123"
    assert result["persistenceStatus"] == "live"
    assert result["routeDecision"]["rerouted"] is False


def test_false_green_responses_are_rejected():
    mutations = [
        lambda data: data.update(model="wrong-model"),
        lambda data: data["roxy"]["routeDecision"].update(selectedModel="wrong-model"),
        lambda data: data["roxy"]["routeDecision"].update(rerouted=True),
        lambda data: data["roxy"].update(degradedFallback=True),
        lambda data: data["roxy"].update(harnessBypassDetected=True),
        lambda data: data["roxy"].update(harnessEnforced=True),
        lambda data: data["roxy"].update(sessionId=""),
        lambda data: data["roxy"].update(persistenceStatus="failed"),
        lambda data: data["roxy"].update(memoryStatus="missing"),
        lambda data: data["roxy"].update(identityCapsuleApplied=False),
        lambda data: data["choices"][0].update(finish_reason="length"),
        lambda data: data.update(timings={}),
        lambda data: data["choices"][0]["message"].update(content=""),
    ]
    for mutate in mutations:
        data = valid_response()
        mutate(data)
        result = validate_harness_response(data, MODEL)
        assert not result["ok"]
        assert result["failures"]


def test_lane_selection_and_native_provenance_widget():
    service = ChatService()
    service.set_lane("frontier")
    assert service.selected_lane == "frontier"
    assert service._resolve_model() == MODEL

    widget = ChatMessage_Widget(
        ChatMessage(
            id="message-1",
            role="assistant",
            content="contract response",
            timestamp=datetime.now(),
            model=MODEL,
            latency_ms=321,
            route_summary=f"{MODEL}->{MODEL} rerouted=False",
            persistence_status="live",
            session_id="roxy_contract_123",
            provider_tps=25.0,
            receipt_path="/tmp/rcc-chat-contract.json",
        )
    )
    assert widget.get_first_child() is not None


def test_health_timeout_is_bounded_without_shortening_generation_timeout():
    short = ChatService(health_timeout_seconds=0)
    long = ChatService(health_timeout_seconds=999)
    assert short.health_timeout_seconds == 1
    assert long.health_timeout_seconds == 10
    assert short._soup_session.get_property("timeout") == 120


def test_dead_proxy_keeps_talk_column_usable_and_shows_error():
    service = ChatService(
        proxy_base_url="http://127.0.0.1:9",
        health_timeout_seconds=1,
    )
    column = TalkColumn(chat_service=service)
    context = GLib.MainContext.default()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if (
            service.status == ConnectionStatus.ERROR
            and "❌" in column._ollama_chip.get_label()
        ):
            break
        time.sleep(0.01)

    assert service.proxy_base_url == "http://127.0.0.1:9"
    assert service.health_timeout_seconds == 1
    assert service.status == ConnectionStatus.ERROR
    assert "Error" in column._status_chip.get_label()
    assert column._status_label.get_label()
    assert "127.0.0.1:9" in column._ollama_chip.get_label()
    assert "http://127.0.0.1:9" in column._ollama_chip.get_tooltip_text()
    assert column.entry.get_sensitive()
    column.entry.set_text("dead harness does not disable native controls")
    assert column.entry.get_text() == "dead harness does not disable native controls"


def run_live_contract() -> dict:
    marker = "ADA_NATIVE_LIVE_CONTRACT_OK"
    payload = build_harness_payload(
        [{"role": "user", "content": f"Return exactly {marker}."}],
        MODEL,
    )
    payload["temperature"] = 0
    payload["max_tokens"] = 64
    request = urllib.request.Request(
        "http://127.0.0.1:4001/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    validated = validate_harness_response(data, MODEL)
    assert validated["ok"], validated["failures"]
    assert validated["content"].strip() == marker
    return validated


def run_live_talk_column() -> dict:
    column = TalkColumn()
    context = GLib.MainContext.default()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if column._chat_service.status in (ConnectionStatus.CONNECTED, ConnectionStatus.ERROR):
            break
        time.sleep(0.01)
    assert column._chat_service.status == ConnectionStatus.CONNECTED
    assert column._chat_service.model == MODEL
    return {"status": column._chat_service.status.value, "model": column._chat_service.model}


def main() -> int:
    Gtk.init()
    test_payload_uses_openai_messages_and_session()
    test_valid_route_is_accepted()
    test_false_green_responses_are_rejected()
    test_lane_selection_and_native_provenance_widget()
    test_health_timeout_is_bounded_without_shortening_generation_timeout()
    test_dead_proxy_keeps_talk_column_usable_and_shows_error()
    if "--live" in sys.argv:
        live = run_live_contract()
        print(
            json.dumps(
                {
                    "model": live["model"],
                    "sessionId": live["sessionId"],
                    "persistenceStatus": live["persistenceStatus"],
                    "routeDecision": live["routeDecision"],
                },
                indent=2,
            )
        )
    if "--live-ui" in sys.argv:
        print(json.dumps(run_live_talk_column(), indent=2))
    print("RCC_CHAT_HARNESS_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
