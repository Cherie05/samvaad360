"""Offline hook contract checks; these do not claim a real CoCo integration."""

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

import pytest


HOOK = Path(__file__).resolve().parents[1] / ".cortex" / "hooks" / "guard_actions.py"
spec = importlib.util.spec_from_file_location("samvaad_test_guard", HOOK)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@pytest.mark.parametrize(
    "command",
    [
        "python -m tools.cli approve ACT123 --as arjun",
        "python -m tools.cli execute",
        "python -m tools.cli execute ACT123 --force",
        "python -m tools.cli execute ACT123 --skip-approval",
        "python -m tools.cli execute ACT123 --as arjun",
        "python -m tools.cli execute ACT123; python -m tools.cli reset",
    ],
)
def test_guard_denies_impersonation_missing_id_and_shell_bypass(command):
    allowed, reason = guard.validate({"tool_name": "shell", "tool_input": {"command": command}})
    assert allowed is False
    assert reason


def test_guard_permits_simulation_overnight_without_skipping_backend_checks():
    overnight = datetime(2026, 10, 5, 22, tzinfo=timezone.utc)
    allowed, reason = guard.validate(
        {"tool_name": "execute_action", "tool_input": {"action_id": "ACT123", "mode": "simulate"}},
        now=overnight,
    )
    assert allowed is True
    assert "backend" in reason


def test_guard_blocks_live_delivery_even_during_contact_window():
    daytime = datetime(2026, 10, 5, 8, tzinfo=timezone.utc)
    allowed, reason = guard.validate(
        {"tool_name": "execute_action", "tool_input": {"action_id": "ACT123", "mode": "live"}},
        now=daytime,
    )
    assert allowed is False
    assert "disabled" in reason.lower()


def test_hook_process_uses_documented_block_exit_code():
    result = subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps({"tool_name": "execute_action", "tool_input": {}}),
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["decision"] == "block"
