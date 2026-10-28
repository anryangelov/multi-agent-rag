"""Shared test setup."""

from pydantic_ai import models

# A safety catch from the PydanticAI testing guide: a test that builds a real
# model (Anthropic, Azure) and runs it fails at once instead of calling out.
# FunctionModel, the offline stand-in, is allowed.
models.ALLOW_MODEL_REQUESTS = False
