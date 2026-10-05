"""CoCo advisory guard. The application service remains the authority.

Reads the documented structured PreToolUse JSON context from stdin. This
recognizes the approved CLI form; it does not sandbox a general shell.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def validate(payload: dict, now: datetime | None = None) -> tuple[bool, str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        return False, "Expected structured tool_input JSON for the action guard."
    values = payload["tool_input"]
    command = values.get("command", "")
    name = str(payload.get("tool_name", ""))
    action_id = values.get("action_id")
    mode = values.get("mode", "simulate")
    targeted = name == "execute_action"
    if command:
        if not isinstance(command, str):
            return False, "Shell command must be a string."
        if "tools.cli" not in command:
            return True, "No Samvaad action execution in this tool call."
        try:
            arguments = shlex.split(command, posix=True)
        except ValueError:
            return False, "Cannot parse the Samvaad command."
        try:
            module = arguments.index("tools.cli")
            operation = arguments[module + 1]
        except (ValueError, IndexError):
            return False, "Samvaad command is missing an operation."
        if operation == "approve":
            return False, "Approval is a manual operator action. CoCo must not impersonate a manager or credit officer."
        if operation != "execute":
            return True, "No action execution in this Samvaad command."
        targeted = True
        if any(marker in command for marker in (";", "\n", "\r", "&&", "||", "|", "&", "$(", "`")):
            return False, "Execute a single explicit CLI action without shell chaining or substitution."
        rest = arguments[module + 2:]
        if not rest or rest[0].startswith("-"):
            return False, "An explicit action ID is required."
        action_id = rest[0]
        for index, item in enumerate(rest):
            if item in {"--force", "--skip-approval", "--bypass", "--as", "--role"} or item.startswith("--force="):
                return False, "Execution cannot force, bypass approval, or select an operator identity."
            if item == "--mode":
                if index + 1 >= len(rest):
                    return False, "Execution mode is missing its value."
                mode = rest[index + 1]
            elif item.startswith("--mode="):
                mode = item.split("=", 1)[1]
    if not targeted:
        return True, "No action execution in this tool call."
    if not isinstance(action_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", action_id):
        return False, "A valid explicit action ID is required."
    if values.get("force") or values.get("skip_approval") or values.get("role"):
        return False, "Force, approval bypass, or caller-selected roles are not permitted."
    if mode != "simulate":
        stamp = now or datetime.now(IST)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=IST)
        local = stamp.astimezone(IST)
        if not 8 <= local.hour < 19:
            return False, "Live contact is allowed only from 08:00 to 19:00 IST. Simulation is exempt."
        return False, "Live provider delivery is disabled in this local build. Use --mode simulate."
    return True, "Simulation permitted; backend approval, consent, eligibility, and idempotency checks still apply."


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        allowed, reason = validate(payload)
    except (ValueError, TypeError):
        allowed, reason = False, "Invalid structured hook input."
    print(json.dumps({"decision": "allow" if allowed else "block", "reason": reason}))
    return 0 if allowed else 2


if __name__ == "__main__":
    sys.exit(main())
