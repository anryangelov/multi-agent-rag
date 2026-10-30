"""Ask the documentation one question from the command line.

    uv run python -m rag_system "How long can we keep API debug logs?"
    uv run python -m rag_system --clearance confidential "..."

    1. Assistant() builds the system from .env (app.py)
    2. stderr: which models run
    3. stdout: the answer, its sources and any warnings, as Markdown

The model names go to stderr, so stdout holds only the answer.
"""

import argparse
import asyncio
import os
import sys

from rag_system.app import Assistant, as_markdown
from rag_system.config import Settings
from rag_system.messages import Classification


def main(argv: list[str] | None = None, settings: Settings | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m rag_system",
        description="Answer a question from the bank's platform documentation.",
    )
    parser.add_argument("question")
    parser.add_argument(
        "--clearance",
        choices=[level.value for level in Classification],
        default=Classification.INTERNAL.value,
        help="the asker's clearance; documents above it are not searched",
    )
    args = parser.parse_args(argv)
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

    assistant = Assistant(settings)
    print(assistant.describe(), file=sys.stderr)
    try:
        answer = asyncio.run(
            assistant.ask(args.question, Classification(args.clearance))
        )
    except ValueError as error:  # an empty question
        parser.error(str(error))
    print(as_markdown(answer))


if __name__ == "__main__":
    main()
