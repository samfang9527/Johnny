from __future__ import annotations

import argparse
import os
import sys

from src.api.dependencies import CurrentUser, build_request_companion_agent, ensure_current_user
from src.infrastructure.database.models import Base
from src.infrastructure.database.session import create_database_engine, create_session_factory, get_database_url
from src.infrastructure.llm.settings import load_llm_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Johnny AI companion conversation smoke.")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--message", default="How should I adjust today's training?")
    parser.add_argument("--live-openai", action="store_true", help="Require OpenAI settings and make a live model call.")
    args = parser.parse_args()

    if args.live_openai:
        settings = load_llm_settings()
        if settings is None:
            print("LLM_PROVIDER=openai, LLM_MODEL, and OPENAI_API_KEY or LLM_API_KEY are required for --live-openai.", file=sys.stderr)
            return 2
    else:
        os.environ.pop("LLM_PROVIDER", None)

    database_url = get_database_url()
    engine = create_database_engine(database_url)
    if database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    session_factory = create_session_factory(database_url)

    with session_factory() as session:
        ensure_current_user(session, CurrentUser(id=args.user_id))
        run = build_request_companion_agent(session).run_conversation(user_id=args.user_id, message=args.message)
        session.commit()

    print(f"run_id={run.id}")
    print(f"status={run.status}")
    print(f"provider={run.provider}")
    print(f"model={run.model}")
    print(f"recommendation_id={run.recommendation_id or ''}")
    print(f"output={run.output_summary or run.error_message or ''}")
    return 0 if run.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
