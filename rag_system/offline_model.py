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
    TextPart,
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
# How the orchestrator writes a claim into the synthesis prompt.
_CLAIM = re.compile(
    r'<claim domain="(?P<domain>[^"]+)" sources="(?P<sources>[^"]+)">'
    r"(?P<text>.*?)</claim>"
)
OFFLINE_NOTE = (
    "Offline answer: composed by template from the agents' claims; "
    "no language model was used, so contradictions are not detected."
)
# How the orchestrator writes a settled conflict into the synthesis prompt.
_CONFLICT = re.compile(r"<conflict>(?P<sentence>.*?)</conflict>")
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
        case "conflicts":
            # Telling a contradiction from two related claims needs a
            # language model; measured heuristics flag mostly false pairs.
            output = {"pairs": []}
        case "evidence":
            output = {"labels": _no_support(prompt)}
        case "text":
            return ModelResponse(parts=[TextPart(_answer_from_claims(prompt))])
        case _:
            raise OfflineModelError(f"the offline model has no template for {asked}")
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])


def _answer_from_claims(prompt: str) -> str:
    """One paragraph per domain: its claims, each followed by its sources;
    then one paragraph per settled conflict, as the orchestrator wrote it."""
    paragraphs = {}
    for match in _CLAIM.finditer(prompt):
        cited = " ".join(f"[{doc_id}]" for doc_id in match["sources"].split())
        sentence = f"{match['text']} {cited}"
        paragraphs.setdefault(match["domain"], []).append(sentence)
    lines = [OFFLINE_NOTE]
    for domain, sentences in paragraphs.items():
        lines.append(f"{domain.capitalize()}: " + " ".join(sentences))
    for match in _CONFLICT.finditer(prompt):
        lines.append(match["sentence"])
    return "\n\n".join(lines)


def _no_support(prompt: str) -> list[dict]:
    """Every passage of the judge's prompt labelled as supporting neither side."""
    return [
        {"chunk_id": match["id"], "supports": "neither"}
        for match in _CHUNK.finditer(prompt)
    ]


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
        sentence = _first_sentence(match["text"])
        if sentence:
            claims.append({"text": sentence, "chunk_ids": [match["id"]]})
    return claims


def _first_sentence(chunk_text: str) -> str:
    """The first sentence of the first paragraph of prose.

    Skips the document title (the first paragraph) and headings, and drops
    markdown bold. A chunk with only a table gives the table's rows.
    """
    body = ""
    table = ""
    for paragraph in chunk_text.split("\n\n")[1:]:
        paragraph = paragraph.strip()
        if paragraph.startswith("|") and not table:
            table = paragraph
        elif paragraph and not paragraph.startswith("#"):
            body = " ".join(paragraph.replace("**", "").split())
            break
    if not body and table:
        return _table_as_sentence(table)
    number = _LIST_NUMBER.match(body)
    list_number = number.group() if number else ""
    rest = body[len(list_number) :]
    sentence = list_number + _SENTENCE_END.split(rest, maxsplit=1)[0]
    words = sentence.split()
    if len(words) > CLAIM_WORDS:
        return " ".join(words[:CLAIM_WORDS]) + " ..."
    return " ".join(words)


def _table_as_sentence(table: str) -> str:
    """'| A | B |' rows as 'A: a1, B: b1; A: a2, B: b2.', cut like a claim.

    The first line holds the column names, the second the |---| line.
    """
    lines = [line.strip().strip("|") for line in table.splitlines()]
    header = [cell.strip() for cell in lines[0].split("|")]
    rows = []
    for line in lines[2:]:
        cells = [cell.strip().replace("**", "") for cell in line.split("|")]
        pairs = []
        for name, cell in zip(header, cells, strict=False):
            pairs.append(f"{name}: {cell}")
        rows.append(", ".join(pairs))
    words = ("; ".join(rows) + ".").split()
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
