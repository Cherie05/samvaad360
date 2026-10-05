"""Local developer CLI. Automation cannot select an approver identity."""

from __future__ import annotations

import argparse
import json
import sys

from samvaad.factory import create_service


def _print(value):
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Samvaad 360 synthetic local demo controls")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("seed", help="Seed the standard 20-customer local synthetic demo")
    commands.add_parser("status", help="Show portfolio and pending/executed actions")
    recommend = commands.add_parser("recommend", help="Generate a guarded action as demo analyst Meera")
    recommend.add_argument("customer_id")
    approve = commands.add_parser("approve", help="Manual local demo approval; separate from automation execution")
    approve.add_argument("action_id")
    approve.add_argument("--as", dest="approver", required=True, choices=["arjun", "kavya"], help="Explicitly simulate manager Arjun or credit officer Kavya")
    approve.add_argument("--decision", choices=["APPROVE", "REJECT"], default="APPROVE")
    approve.add_argument("--note", default="Manual local developer demo approval")
    execute = commands.add_parser("execute", help="Execute one approved action as the fixed automation principal")
    execute.add_argument("action_id")
    execute.add_argument("--mode", choices=["simulate"], default="simulate")
    execute.add_argument("--outcome", choices=["ACCEPT", "DECLINE", "CALLBACK", "OPT_OUT", "NO_ANSWER", "ALREADY_PAID", "FAILED"], default="ACCEPT")
    ask = commands.add_parser("ask", help="Ask an evidence-grounded local question")
    ask.add_argument("question")
    ask.add_argument("--customer-id", default=None)
    commands.add_parser("check", help="Run read-only seeded-data and guard sanity checks")
    reset = commands.add_parser("reset", help="Reset only the local synthetic database")
    reset.add_argument("--confirm", required=True, choices=["RESET-LOCAL-DEMO"])
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    service = create_service()
    try:
        if args.command == "seed":
            value = service.seed_demo(service.resolve_actor("demo-admin"))
        elif args.command == "reset":
            value = service.reset_demo(service.resolve_actor("demo-admin"))
        elif args.command == "status":
            value = {"portfolio": service.portfolio(), "actions": service.actions()}
        elif args.command == "recommend":
            value = service.recommend(args.customer_id, service.resolve_actor("meera"))
        elif args.command == "approve":
            value = service.approve_action(args.action_id, service.resolve_actor(args.approver), decision=args.decision, note=args.note)
        elif args.command == "execute":
            value = service.execute_action(args.action_id, service.resolve_actor("local-runner"), mode=args.mode, outcome=args.outcome)
        elif args.command == "ask":
            value = service.ask(args.question, customer_id=args.customer_id, actor=service.resolve_actor("meera"))
        else:
            customers = service.list_customers()
            invalid = []
            for row in customers:
                customer_id = row.get("customer_id")
                if not customer_id:
                    invalid.append("Customer row lacks customer_id")
                    continue
                record = service.customer360(customer_id)
                if not record.get("customer"):
                    invalid.append(f"Missing 360 profile: {customer_id}")
            # The executor never becomes a manager/credit identity through CLI flags.
            executor = service.resolve_actor("local-runner")
            if executor.role != "AUTOMATION":
                invalid.append("Automation principal has unexpected role")
            value = {"passed": not invalid and len(customers) >= 3, "customer_count": len(customers), "errors": invalid, "external_delivery": "disabled", "check_scope": "read-only fixture and identity sanity; run pytest for behavioral verification"}
            _print(value)
            return 0 if value["passed"] else 1
        _print(value)
        return 0
    except Exception as exc:
        code = getattr(exc, "code", None)
        if not code:
            raise
        _print({"error": str(code), "message": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
