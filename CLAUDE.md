# multi-agent-rag: project context for Claude Code

> Read this whole file at the start of every session. [DECIDED] items are
> the developer's decisions: follow them. [DIRECTION] items are the course
> the developer has set; the details come later.

---

## Meta-principle

**Every decision must pay rent.** Name the concrete problem it solves (for
the reviewer, the developer or the agent) or do not add it. This is a
one-week technical assignment, not a product: simple, boring and visible
wins.

**The developer owns the design and makes every design decision; you (the
agent) implement them.** Decisions live in this file and in
`docs/decisions.md`, not in your head.

---

## What this project is

A technical assignment with two deliverables in one public GitHub repo.

1. **Task A, code:** a simulated multi-agent RAG system over synthetic
   documents in three domains (technical, business, compliance):
   - components: query classifier, three domain RAG agents, orchestrator,
     vector store manager;
   - capabilities: agent communication protocol, query decomposition,
     dynamic retrieval, result synthesis, a simulated learning mechanism
     (feedback adjusts weights);
   - advanced: conflict resolution with confidence scores, citation
     tracking, knowledge updates, performance monitoring;
   - shown in `notebooks/demo.ipynb`, which must run end to end.
2. **Task B, document:** `systems_design/self_service_paradox.md`. One
   workflow automation platform that serves both business users (drag and
   drop, templates, wizards) and power users (code, API, custom logic).

Evaluation: correctness and completeness, code quality and architecture,
understanding of RAG and multi-agent concepts, error handling; for Task B:
architecture quality, trade-offs, feasibility, long-term thinking.

**Constraints confirmed with the assignment's authors:**
- The demo may call an external LLM with a key the reviewer provides.
- Target environment: models on Azure OpenAI, everything else on-premise.
- The given repo structure may be changed.

### [DECIDED] One world for both tasks

The synthetic corpus of Task A is the internal documentation of the
automation platform designed in Task B: how to deploy a component, who
approves a new process, the rules for data and the cloud LLM. The RAG
system is then the assistant for that platform, and both deliverables tell
one story. The setting: a fictional bank with legacy core systems, models
on Azure OpenAI, everything else on-premise.

---

## Workflow

- **Design decisions are the developer's.** Before any first-time
  decision, anything that becomes a pattern, the corpus design or any
  deviation from this file, stop and bring it to the developer. Record the
  developer's decision as a short entry in `docs/decisions.md` (the
  decision, why, the rejected options with one reason each) and add
  standing rules to this file.
- Without asking, apply an established pattern, do mechanical work and fix
  unambiguous test failures.
- Never commit before the developer has seen the diff and approved it.
  Commit format: `<area>: <what changed>`.
- The repo is public. Never commit `.env`; commit `.env.example` with
  empty values. `scratch/` is gitignored and holds private notes and
  throwaway spikes.

---

## Writing style for everything in the repo

README, docs, the systems design and comments are read by reviewers.

- Plain, direct sentences. No marketing words ("robust", "seamless",
  "leverage", "comprehensive", "cutting-edge"), no filler intros, **no em
  dashes** (grep for "—" before showing any draft).
- Every claim in the README is backed by code, a test or an eval number.
- Docstrings carry ASCII flow diagrams where a flow exists.
- The README has a section **"Assumptions and questions I would ask the
  business"**: what was unclear, what was assumed, which alternative was
  considered.
- `CLAUDE.md` and `docs/decisions.md` are committed: they show how the
  work with an AI coding agent was organised (decisions by the developer,
  recorded and tested). The README says so in one sentence.

---

## [DECIDED] Architecture

Decided by the developer.

1. **PydanticAI only at the LLM boundary; orchestration is plain Python.**
   The orchestrator calls the classifier, then the domain agents (in
   parallel, `asyncio.gather`), then synthesis, as visible numbered steps.
   No agent-as-tool delegation where the model decides the routing: the
   reviewer evaluates the orchestration, so it must be readable code. No
   LangChain, LangGraph or LlamaIndex.
2. **Models are injected, never imported.** One factory per model kind
   builds the PydanticAI model or the embedder from settings; everything
   else receives it as a parameter.
   - `LLM_PROVIDER`: `offline` (default; a `FunctionModel` that composes
     the answer from the retrieved chunks by template) | `anthropic` |
     `azure`.
   - `EMBEDDING_PROVIDER`: `local` (default; small model downloaded on
     first run, never committed) | `azure`.
   - Azure needs key, endpoint, api-version and deployment names (the
     "model" on Azure is the deployment name).
   - pydantic-settings validates at startup that the chosen provider has
     its credentials, and fails loudly if not.
   - A new provider (e.g. a local LLM on-premise) is one enum value plus
     one `case` in the factory.
3. **Production target: Azure OpenAI for both models; everything else
   on-premise.** Development uses Anthropic plus local embeddings. One
   verification run against Azure before submission, so the README can
   honestly say "tested against Azure OpenAI" (if the Azure trial gets no
   model quota, the README says the Azure path is untested).
4. **The index remembers its embedding model.** Vectors from different
   models cannot be compared. In the demo one injected embedder builds the
   in-memory index and embeds every query, so the index only records and
   shows the model name; the production design (pgvector) stores the
   model next to the vectors and refuses a query from another model.
5. **Repo structure:** every file from the assignment's structure exists
   and stays the entry point; we add around it. Planned additions:
   `rag_system/messages.py` (the agent communication protocol: Pydantic
   models such as `SubQuery`, `AgentAnswer`, `Citation`),
   `rag_system/config.py`, `data/` (the corpus), `tests/unit/`,
   `tests/evals/`, `docs/decisions.md`. Learning, monitoring and knowledge
   updates get their own modules when they appear; `utils.py` holds only
   truly generic helpers.
6. **The notebook runs with no key and no `.env`.** The design targets the
   model mode; the offline mode is a deterministic stand-in for tests and
   key-less runs (templated answers) and says so. The committed notebook
   carries the outputs of a real model run.
7. **Floors, top-down.** Each file answers one question. `orchestrator.py`
   is START HERE ("what happens when a question arrives?"); one floor down
   `query_classifier.py` and `domain_agents.py`; below them
   `vector_store.py`. Each module opens with a docstring map (ASCII
   diagram); the entry function reads as numbered steps matching the map.
   A logic module over ~400 lines or a function over ~50 lines is split by
   floor before more is added.
8. **Constructor injection.** All non-determinism enters as a parameter:
   the models, time (`now`), random seeds. Tests never patch.
9. **Closed sets of values are `StrEnum`s,** with the behaviour that
   belongs to them inside the enum (`Classification.allows`,
   `Domain.prefix`). No `Literal` for domain values: a typo in our own code
   fails at once without a type checker, and the JSON stays the same.
10. **PydanticAI the way its documentation shows it.** One module-level
    `Agent` per model role (no model on it), validators attached with
    `@agent.output_validator` next to their function, and the injected
    model passed at every run: `agent.run(prompt, model=..., deps=...,
    timeout=...)`. Every structured output is named
    (`ToolOutput(Plan, name="plan")`); the offline model picks its template
    by that name, or "text" for a free-text answer (the synthesis). Tests set
    `models.ALLOW_MODEL_REQUESTS = False` (`tests/conftest.py`).
11. **Worked examples in the entry methods.** The method that runs a
    module's numbered steps carries, under each step, an "Example" comment
    that follows one real eval question through it: what goes in, what
    comes out. An eval test checks the example's values, so a comment that
    goes stale fails the tests. The ~50-line limit counts code lines, not
    these comments.

---

## [DIRECTION] Task B, the systems design

The developer has set this course; the full design comes later.

1. **Three personas, not two:** business user, process analyst (assembles
   templates from ready-made blocks), developer (builds blocks, connectors,
   custom logic). The analyst is the bridge the brief leaves out.
2. **One model, many views.** A workflow is one definition; the canvas,
   the wizard and the code are views over it, not separate systems.
   Progressive disclosure moves a user between views, never between
   systems.
3. **Connectors are the core.** A modern system gets an API connector; a
   legacy system without an API gets an RPA connector; the AI step is a
   connector to Azure with rules on which data classes it may receive.
   Business users see only approved connectors.
4. **Governance without heavy process:** tiers for templates and
   connectors (certified / team / experimental), four-eyes review for
   anything touching sensitive data, audit of every run.
5. **Migration from today:** how existing automated processes enter the
   model, instead of building from zero.

---

## [CURRENT] Tooling

- uv for development (`pyproject.toml` + `uv.lock`); `requirements.txt`
  generated with `uv export` for the reviewer (the assignment asks for it).
- Ruff for lint and format; pytest with pytest-asyncio.
- Expected dependencies: pydantic, pydantic-settings, pydantic-ai, numpy,
  the embedding library, jupyter.

---

## Testing

- Tests first, then implementation, tight loop until green. Run pytest
  before calling anything done.
- Test behaviour through the public surface, never internals. No mocking
  of our own code; the offline `FunctionModel` is the test model.
- Three layers:
  - `tests/unit/`: each component on its own.
  - `tests/test_scenarios.py` (the assignment's file): the three example
    questions end to end, offline, deterministic.
  - `tests/evals/`: a gold set (`questions.yaml`: expected domains,
    expected documents, expected answer facts). Offline evals always run
    (classifier accuracy, retrieval hit@k, citation validity, conflict
    winner). LLM evals (`@pytest.mark.eval`) run only with a key and are
    skipped otherwise. The eval numbers feed performance monitoring and the
    learning demo.
- Error handling and edge cases are tested: empty query, no domain
  matched, an agent fails or times out, no documents retrieved, provider
  misconfigured, embedding model mismatch.
