"""Set or reset an account's password.

There is no self-service password reset (no mail transport is configured), so
this is the supported way to give an account password sign-in — including a
GitHub-linked account that has none, which is what an operator needs to reach
the admin dashboard without GitHub.

    python scripts/set_password.py you@example.com
    python scripts/set_password.py you@example.com --create --name "Your Name"

The password is read from a prompt by default so it never lands in shell
history. ``--password`` exists for automation and is echoed nowhere.

Being an admin is separate: that comes from the ADMIN_EMAILS allowlist, not
from anything stored on the account.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.session import init_db, session_scope
from app.schemas.auth import MIN_PASSWORD_LENGTH


def _validate(password: str) -> str | None:
    """Same policy the register endpoint enforces."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "Password must contain at least one letter and one number"
    if password.strip() != password:
        return "Password must not start or end with whitespace"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Set an account password")
    parser.add_argument("email", help="Account email address")
    parser.add_argument("--password", help="Read from a prompt when omitted")
    parser.add_argument("--create", action="store_true", help="Create the account if absent")
    parser.add_argument("--name", default="", help="Display name when creating")
    args = parser.parse_args()

    password = args.password or getpass.getpass("New password: ")
    problem = _validate(password)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    configure_logging()
    init_db()

    from app.models.entities import User, utcnow
    from app.services import auth as auth_service

    email = args.email.strip().lower()

    with session_scope() as session:
        user = auth_service.find_user_by_email(session, email)

        if user is None:
            if not args.create:
                print(
                    f"error: no account for {email}. Pass --create to make one.",
                    file=sys.stderr,
                )
                return 1
            user = User(
                email=email,
                name=args.name or email.split("@", 1)[0],
                login=auth_service._login_from_email(session, email),
            )
            action = "created"
        else:
            action = "updated"

        user.password_hash = hash_password(password)
        user.updated_at = utcnow()
        session.add(user)
        session.commit()
        session.refresh(user)

        is_admin = settings.is_admin_email(user.email)
        print(f"Password {action} for {user.email} (login: {user.login})")
        print(f"  admin: {'yes' if is_admin else 'no'}")
        if not is_admin:
            print(
                "  note: add this address to ADMIN_EMAILS to grant the admin dashboard.",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
