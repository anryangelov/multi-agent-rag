"""What answers in place of a language model when there is no key?

The offline mode is a deterministic stand-in for the tests and for runs
without a key. Every component calls its PydanticAI agent the same way in
both modes; without a key the agent's model is this function. It sees what
a real model would see: the prompt our code wrote and the output asked for.

    component --> agent.run(prompt)
              --> offline model
                    1. which output is asked for? (the name of its schema,
                       e.g. Plan; "text" when free text is asked for)
                    2. the template for that output fills it from the prompt
              <-- the output, in the shape a real model returns it

The answers are templates, not understanding. A request with no template
fails loudly instead of returning something made up.
"""

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel


class OfflineModelError(RuntimeError):
    """The offline model was asked for an output it has no template for."""


def offline_model() -> FunctionModel:
    return FunctionModel(_answer, model_name="offline")


def _answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    # 1. Which output is asked for?
    asked = _asked_output(info)
    # 2. No template exists yet for any output.
    raise OfflineModelError(f"the offline model has no template for {asked}")


def _asked_output(info: AgentInfo) -> str:
    if info.output_tools:
        return info.output_tools[0].parameters_json_schema["title"]
    return "text"
