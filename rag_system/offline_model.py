"""What answers in place of a language model when there is no key?

The offline mode is a deterministic stand-in for the tests and for runs
without a key. Every component calls its PydanticAI agent the same way in
both modes; without a key the agent's model is this function. It sees what
a real model would see: the prompt our code wrote and the output asked for.

    component --> agent.run(prompt)
              --> offline model
                    1. which output is asked for? (the name of its output
                       tool, e.g. "plan"; "text" when free text is asked for)
                    2. the template for that output fills it from the prompt
              <-- the output, in the shape a real model returns it

The answers are templates, not understanding. A request with no template
fails loudly instead of returning something made up.
"""

import re

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from rag_system.messages import Domain


class OfflineModelError(RuntimeError):
    """The offline model was asked for an output it has no template for."""


def offline_model() -> FunctionModel:
    return FunctionModel(_answer, model_name="offline")


# How domain_agents and query_classifier write a chunk into their prompts;
# the classifier also writes the chunk's domain.
_CHUNK = re.compile(
    r'<chunk id="(?P<id>[^"]+)"(?: domain="(?P<domain>[^"]+)")?>\n'
    r"(?P<text>.*?)\n</chunk>",
    re.DOTALL,
)
_QUESTION = re.compile(r"^Question: (?P<question>.*)$", re.MULTILINE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# "1. " at the start of a list item is not the end of a sentence.
_LIST_NUMBER = re.compile(r"^\d+\.\s+")
CLAIM_WORDS = 40  # a templated claim is cut after this many words


def _answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    # 1. Which output is asked for?
    asked = _asked_output(info)
    prompt = _last_prompt(messages)
    # 2. The template for that output.
    match asked:
        case "plan":
            output = {"sub_queries": _plan_from_chunks(prompt)}
        case "claims":
            output = {"claims": _claims_from_chunks(prompt)}
        case _:
            raise OfflineModelError(f"the offline model has no template for {asked}")
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])


def _plan_from_chunks(prompt: str) -> list[dict]:
    """Every domain of the chunks, in the order technical, business,
    compliance; each one gets the whole question."""
    question = _QUESTION.search(prompt)["question"]
    found = {match["domain"] for match in _CHUNK.finditer(prompt)}
    sub_queries = []
    for domain in Domain:
        if domain in found:
            sub_queries.append({"domain": domain, "text": question})
    return sub_queries


def _claims_from_chunks(prompt: str) -> list[dict]:
    """One claim per chunk: the first sentence of its text, citing the chunk."""
    claims = []
    for match in _CHUNK.finditer(prompt):
        claims.append(
            {"text": _first_sentence(match["text"]), "chunk_ids": [match["id"]]}
        )
    return claims


def _first_sentence(chunk_text: str) -> str:
    """Skip the document title and the headings, then take one sentence."""
    paragraphs = chunk_text.split("\n\n")[1:]  # the first one is the title
    body = " ".join(p for p in paragraphs if not p.startswith("#")).strip()
    number = _LIST_NUMBER.match(body)
    list_number = number.group() if number else ""
    rest = body[len(list_number) :]
    sentence = list_number + _SENTENCE_END.split(rest, maxsplit=1)[0]
    words = sentence.split()
    if len(words) > CLAIM_WORDS:
        return " ".join(words[:CLAIM_WORDS]) + " ..."
    return " ".join(words)


def _last_prompt(messages: list[ModelMessage]) -> str:
    """The text of the last user prompt our code sent."""
    prompts = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                prompts.append(part.content)
    return prompts[-1] if prompts else ""


def _asked_output(info: AgentInfo) -> str:
    """The name each component gives its output, e.g. ToolOutput(Plan, name="plan")."""
    if info.output_tools:
        return info.output_tools[0].name
    return "text"
