"""Small shared types. Identity must be resolved by the entry point."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    user_id: str
    role: str


class ActionError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


DEMO_ACTORS = {
    "meera": Actor("meera", "ANALYST"),
    "arjun": Actor("arjun", "MANAGER"),
    "kavya": Actor("kavya", "CREDIT"),
    "farah": Actor("farah", "ANALYST"),
    "local-runner": Actor("local-runner", "AUTOMATION"),
    "demo-admin": Actor("demo-admin", "ADMIN"),
}
