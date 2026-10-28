# Design decisions

One entry per decision: what was decided, why, and the options that were
rejected, with one reason each. Sections follow the order in which the
decisions were made.

## Foundations

### One world for both tasks

**Decision.** The Task A corpus is the internal documentation of the
automation platform designed in Task B, at a fictional bank (Orla Bank)
with legacy core systems, models on Azure OpenAI and everything else
on-premise. The two tasks stay separate deliverables.

**Why.** The brief already links them: Task B lets employees "build their
own workflows using microservices", and the Task A test questions ask about
"deploying a new microservice" and "a new data processing workflow".

**Rejected.**
- An unrelated fictional company: two unrelated stories.
- Real public documentation: no control over the contradictions and
  versions that conflict resolution needs; unclear licences.

**Cost accepted.** The corpus fixes parts of the Task B design early (for
example the connector tiers), so the Task B document must agree with it.

### Python version

**Decision.** Develop on Python 3.13; declare `requires-python >=3.12`; run
the tests once on 3.12 and 3.14 before submission.

**Why.** Every dependency has wheels for 3.12 to 3.14 (PyPI, 2026-10-24):
`pydantic-ai-slim` and `onnxruntime` need 3.11 or later, current `numpy`
needs 3.12.

**Rejected.**
- 3.14 only: a reviewer on 3.12 or 3.13 cannot install.
- `>=3.11`: an older `numpy`, a forked lock file and a third test run.

### The corpus

**Decision.** 26 Markdown documents in `data/<domain>/`: 24 structured
ones (8 per domain, 300 to 600 words, with `##` sections) and 2 long
unstructured ones without headings (BUS-9, meeting minutes, and TEC-9, an
incident review, about 1,200 to 1,300 words each). Every document is the
expected answer of at least one eval question.

**Why.** With about 150 chunks, random top-5 retrieval would find the right
document for only about 20% of questions, so retrieval quality can be
measured. 12 documents would give about 37%. The two unstructured
documents stand for the long, unstructured text that much of a bank's
knowledge lives in, and that knowledge updates can bring in at any time.

**Rejected.**
- 12 documents: too easy to tell retrieval methods apart.
- 45 documents: about twice the review time for little gain.

### Deliberate contradictions

**Decision.** Five contradictions are written into the corpus:

| # | Documents | Kind | Resolved in |
|---|---|---|---|
| 1 | TEC-2 vs TEC-3 | an older and a newer version | the technical agent |
| 2 | BUS-1 vs BUS-2 | an older and a newer version | the business agent |
| 3 | TEC-4 vs CMP-3 | a runbook vs a policy | the orchestrator (two domains) |
| 4 | BUS-4 vs BUS-3 | a guide vs a policy | the business agent |
| 5 | TEC-5 vs BUS-3 | a guide vs a policy | the orchestrator (two domains) |

In conflicts 3 and 4 the weaker document is the newer one, so recency alone
picks the wrong answer.

Conflicts 1 and 2 are settled by metadata: the newer version names the
older one in `supersedes`, and search leaves superseded versions out
unless a question asks about history. The conflict rules deal with
conflicts 3, 4 and 5, where nothing in the metadata links the documents.

**Why.** The brief asks to "handle contradictory information from different
sources". A conflict inside one domain reaches one agent; a conflict across
domains only becomes visible when the orchestrator combines the agents'
answers, so both kinds are needed.

**Rejected.**
- Version conflicts only: they do not involve "different sources".
- A conflict with no winner, shown to the user as is: its rule belongs
  with the conflict resolution rules and can be added there.

### Document classification as a retrieval filter

**Decision.** Every document is `public`, `internal` or `confidential`.
The orchestrator passes the caller's clearance down, and the vector store
filters before ranking. Two documents are confidential (BUS-8, CMP-8).

**Why.** In a bank, who may read a document depends on the reader's role.
A document the caller may not see should never reach the agent or the
model.

**Rejected.**
- Only a mention in the README: the corpus and the code would ignore it.
- A label shown in citations without a filter: it would stop nothing.

### Document format

**Decision.** One Markdown file per document with YAML front matter (a
metadata block between two `---` lines at the top): `id`, `title`,
`domain`, `kind`, `version`, `effective_date`, `status`, `supersedes`,
`classification`, `owner`.

**Why.** The text and its metadata live in one file and cannot drift
apart; a wrong date would flip the winner of a conflict.

**Rejected.**
- A separate catalog file: two places for one document.
- Metadata in the file name: long names and no room for `supersedes`.

### Models are injected

**Decision.** `LLM_PROVIDER` (`offline` by default, `anthropic`, `azure`)
and `EMBEDDING_PROVIDER` (`local` by default, `azure`) choose the models.
One factory per model kind builds them; every component receives its model
as a parameter. Settings are validated at startup.

**Why.** The same system runs with no key (the reviewer, the tests), with
Anthropic (development) and with Azure (the target), by changing one
setting. Tests pass the offline model and never patch.

**Rejected.**
- Each module builds its own client at import: with no key the notebook
  fails at import, and tests must patch every module.
- One provider only: a reviewer without that provider can run nothing.

### Azure OpenAI as the production target

**Decision.** Production uses Azure OpenAI for both the language model and
the embeddings; the vector store and the code run on-premise. Development
uses Anthropic and local embeddings. One verification run against Azure
happens before submission, and the README reports its result.

**Why.** This is the target environment confirmed with the assignment's
authors.

**Rejected.**
- Azure only: all work would wait on model quota.
- No Azure run: a weaker claim about exactly the environment that matters.

### Embedding model

**Decision.** `model2vec` with `minishlab/potion-base-8M`.

**Why.** Measured on the first 10 eval questions (23 expected documents,
148 chunks, top 5), with the rule fixed before running: take the lighter
model unless the heavier one finds at least 3 more documents.

| Method | Recall@5 | Packages over numpy | Model | Indexing |
|---|---|---|---|---|
| BM25 (keywords, no model) | 17/23 | about 0 MB | none | 0.01 s |
| `fastembed` + `bge-small-en-v1.5` | 16/23 | +118 MB | 65 MB | 9 to 13 s |
| `model2vec` + `potion-base-8M` | 16/23 | +29 MB | 30 MB | 0.2 s |
| `model2vec` + `potion-retrieval-32M` | 16/23 | +29 MB | 129 MB | 0.5 s |

Searching the top 5 inside each expected domain, as the system does after
decomposition, gives 20/23 for the first three and 22/23 for
`potion-retrieval-32M`. That model is the ready swap if per-domain
retrieval misses documents.

**Rejected.**
- `bge-small-en-v1.5`: no better on this corpus, three times the size;
  the current `onnxruntime` has no wheel for Intel Macs.
- PyTorch-based models (`sentence-transformers`, `granite-embedding`):
  the dependency weight.

**Note.** Keyword search is as good as the embeddings here. The corpus is
small and uses consistent terms; the README says so.

### The index records its embedding model

**Decision.** The index stores the name of the model that built it and
shows it. In production, where the index lives in a database and outlives
the process, a query embedded with another model is refused with a clear
error. In the demo the index is rebuilt at every start by the one injected
embedder that also embeds the queries, so there is no path to a mismatch
and no check to write.

**Why.** Vectors from different models cannot be compared. A check on the
vector size is not enough: `potion-base-8M` gives 256 numbers, and Azure's
`text-embedding-3-small` can be asked for 256 too.

**Rejected.**
- A size check only: misses the case above.
- No check: wrong results with no error.

### Vector store

**Decision.** The demo keeps the vectors in memory with numpy and rebuilds
the index at every start, behind one interface (`add`, `search`). For
production on-premise the README names pgvector; it is not implemented
here.

**Why.** 148 chunks of 256 numbers take 0.15 MB and build in 0.2 s, so a
database solves no problem in the demo. In production, pgvector turns the
class and domain filters into one SQL `WHERE` and updates documents,
metadata and vectors in one transaction, without a new system to run.

**Rejected.**
- Saving the demo index to disk: code to save 0.2 s.
- A real database in the demo: Docker or another dependency for the
  reviewer.
- Qdrant in production: another on-premise system to run for a volume
  that does not need it.

### Repo structure

**Decision.** Every file from the assignment's structure exists and stays
the entry point for its topic. Added around them: `rag_system/messages.py`
(the protocol between agents), `rag_system/config.py` (settings and model
factories), `data/`, `tests/unit/`, `tests/evals/` and this file.

**Why.** The reviewer finds the files the brief names where the brief
puts them.

**Rejected.**
- A `src/` or per-component layout: the brief would have to be mapped onto
  new paths.
- Only the given files: `utils.py` would collect everything else.

## Agents and retrieval

### The role of the offline mode

**Decision.** The design targets the model mode. The offline mode is a
deterministic stand-in for the tests and for runs without a key: answers
are composed by template, every agent receives the whole question, and
conflicts are found with a simple heuristic. The notebook says so, and it
is committed with the outputs of a real model run, which GitHub shows
without running anything.

**Why.** Treating both modes as equals had started to shape the design
around what works without a model.

**Rejected.**
- A key required for the notebook: a reviewer without one runs nothing.
- Both modes as equals: keeps limiting the design.

### Orchestration is plain Python

**Decision.** The orchestrator is async Python with numbered steps: the
classifier plans, the chosen domain agents answer in parallel
(`asyncio.gather`), conflicts are found and resolved, synthesis writes
the answer. PydanticAI is used only where a model is called. Models
understand text (routing, answers, finding conflicting claims, synthesis);
code coordinates and picks conflict winners by explicit rules.

**Why.** The route is a model's decision (the classifier), while its
execution stays readable and is tested offline. The orchestrator meets the
brief's definition: it "coordinates multiple agents and synthesizes their
responses". This is the routing and parallelization pattern described in
Anthropic's ["Building effective agents"](https://www.anthropic.com/research/building-effective-agents).

**Rejected.**
- An LLM orchestrator that calls the domain agents as tools: the route
  differs from run to run, cannot be shown honestly offline, and makes the
  classifier the brief asks for redundant.
- LangGraph, LangChain or LlamaIndex: the route would live in framework
  configuration, plus a heavy dependency.

### Floors, top-down

**Decision.** Each file answers one question. `orchestrator.py` is the
start; `query_classifier.py` and `domain_agents.py` are one floor down;
`vector_store.py` is below them. Each floor calls only the floor below.
Each module opens with an ASCII map that matches the numbered steps of its
entry function. A module over about 400 lines or a function over about 50
is split.

**Why.** A reader opens one file, sees the map and knows where to go next.

**Rejected.**
- Layers by technical type (`models/`, `services/`): one flow spread over
  many folders.
- No maps or limits: files grow until nobody reads them top-down.

### Non-determinism enters through the constructor

**Decision.** Models, the clock and random seeds are constructor
parameters with defaults (`time.perf_counter`, `random.Random(42)`).
Tests pass their own and never patch.

**Why.** Tests, evals and the learning demo give the same numbers on every
run.

**Rejected.**
- Calling `time` and `random` directly and patching in tests: the tests
  depend on module internals.
- A global seed: results depend on the order of the tests.

### Chunking

**Decision.** Documents are cut at `##` sections, with the document title
in front of each chunk. A section over about 250 words, or a document with
no headings, is cut at paragraph boundaries into pieces of about 150
words.

**Why.** Sections are natural boundaries and give precise citations. The
fallback keeps long unstructured text usable: for the two long documents,
section-only chunking sends about 2,700 words to the model per question
and cites the whole document; the fallback sends about 750.

**Measured.** Fixed 120-word windows found the fewest documents (13 of 23
with the embedding model). Whole documents looked best only because a
random top 5 of 8 documents in one domain already finds the right one 62%
of the time. One paragraph of overlap made results worse. With the
fallback, the cause of the incident in TEC-9 sits in a paragraph that
shares no words with the question; the embedding search missed it, and
hybrid search (below) finds it.

**Rejected.**
- Section-only: does not scale to long or unstructured documents.
- Fixed windows: cut sections and tables in half.
- Larger pieces of about 400 words: tuned to one question.

### Choosing domains without a model

**Decision.** Offline, the classifier searches the whole corpus and picks
every domain that holds at least one of the 8 nearest chunks. With a
model, the classifier returns a plan as structured output.

**Why.** A missed domain is a missing part of the answer; an extra domain
costs one agent that answers "nothing relevant". On the 12 eval questions
this method finds all 18 expected domains, with 6 extra ones.

**Rejected.**
- Similarity to a one-sentence description of each domain: found 12 of 18
  and missed the compliance part of all three test scenarios.
- Keywords from document titles: found 10 of 18.
- Always all three domains: classifies nothing.

### Decomposition without a model

**Decision.** Offline, every chosen agent receives the whole question; the
plan still holds one sub-query per domain. With a model, the classifier
rewrites one sub-query per domain.

**Why.** Cutting the question at "and" or "while" lost context and found
fewer documents (19 of 25 against 21): the compliance half of the first
test question lost the word "microservice".

**Rejected.**
- The rule-based split: worse, and shaped to the wording of the three test
  questions.
- A "<domain> rules:" prefix: one document of difference, which is noise.

### Agents talk only to the orchestrator

**Decision.** The orchestrator sends context down (the question, the
agent's sub-query and the caller's clearance) and each agent returns a
partial result up. Agents run in parallel and never talk to each other.

**Why.** It is the orchestrator-worker pattern used in production
systems; [Anthropic's research system](https://www.anthropic.com/engineering/multi-agent-research-system)
notes that its subagents do not coordinate with each other. One model call per agent, easy to test and to
monitor.

**Rejected.**
- A shared blackboard with a second round: twice the model calls and
  slower, with no honest offline version.
- A second round only for conflicts: decided before the conflict rules.

### The messages

**Decision.** `messages.py` defines the plan (one sub-query per domain),
the task an agent receives (question, sub-query, clearance) and the
partial result it returns: a status (`answered`, `nothing_relevant`,
`failed`), a list of claims and a confidence. A claim is one statement
with its citations; a citation carries the document id, title, section,
version, effective date and kind.

**Why.** Every statement knows its source, conflicts are found claim
against claim with the document kind that the rules need, and the status
covers an extra domain and a failed agent.

**Rejected.**
- Free text with citations for the whole answer: no way to tell which
  sentence comes from which document.
- Agents that return only chunks: they would stop being RAG agents.

### Hybrid search

**Decision.** Each agent searches its domain with embeddings and BM25 and
merges the two rankings with reciprocal rank fusion.

**Why.** Per domain on the 12 eval questions (25 expected documents):

| k | Embeddings | BM25 | Hybrid |
|---|---|---|---|
| 3 | 18 | 20 | 20 |
| 5 | 21 | 22 | 22 |
| 8 | 23 | 23 | 24 |

Hybrid is best or equal at every k and finds the TEC-9 cause paragraph.

**Rejected.**
- Embeddings only: weakest at every k.
- BM25 only: no vector store, which the brief asks for.

### Dynamic retrieval

**Decision.** Each agent keeps chunks in hybrid order while their
embedding similarity to the question is at least 0.4, never fewer than 3
or more than 10. The parameters are set per domain; they are equal for
now.

**Why.** On the full offline pipeline it finds 24 of 25 documents with
about 1,080 words to the model, the same as a fixed k of 8 with about
1,370 words. The number of chunks follows the question: from 3 to 10.

**Rejected.**
- k by the number of domains in the plan: 22 of 25, no gain.
- A fixed k: more text, and not dynamic.

**Note.** The 0.4 threshold was chosen on the same 12 questions; the full
gold set checks it. No measurement shows a reason for different values per
domain.

### "Nothing relevant"

**Decision.** Offline, an agent answers `nothing_relevant` when even its
best chunk is below 0.4; with a model, the model may also decide so.

**Why.** It is the same bar as dynamic retrieval. On the 12 questions it
stops 2 of the 6 extra domains and drops no needed one; the lowest needed
domain scores 0.44.

**Rejected.**
- A threshold of 0.51: stops 4 extra domains but cuts 5 needed ones,
  including compliance for the second test scenario.
- No threshold offline: the status would never appear without a key.

### Synthesis and citations

**Decision.** The synthesis receives the agents' claims and writes one
answer that cites document ids in brackets, such as `[TEC-3]`. Code checks
that every cited id belongs to the claims it received, and asks the model
again if not. Code builds the "Sources" list (title, version, date,
section) from the claims' citations.

**Why.** No answer can cite a document the system did not retrieve. This
is the portable form of prompt-based citation; a provider's built-in
citations ([Anthropic's Citations API](https://platform.claude.com/docs/en/build-with-claude/citations))
cannot be combined with structured output and would tie the system to one provider, while production runs on
Azure OpenAI.

**Rejected.**
- Temporary numbers for each claim: an extra layer with no gain for the
  reader.
- Free text without a check: an invented citation would pass unnoticed.

### Superseded versions

**Decision.** A superseded version stays in the index but search leaves it
out by default; a question about history asks for it explicitly
(`include_superseded`).

**Why.** A rule that no longer applies should not take a place in the
results or reach an answer. Old versions are still needed for audit and
for questions such as "how many approvers did a release need in 2025?".

**Rejected.**
- Deleting the old version: no history and no audit trail.
- Searching old versions and letting the conflict rules pick the newer:
  outdated rules take result slots, and a wrong rule would put them in
  the answer.

### The classifier searches before the model decides

**Decision.** In both modes the classifier first searches the whole corpus
and passes the 8 nearest chunks, each with its domain, to the model
together with the question. With a key the model decides the route from
the question and that evidence. Without a key one offline `FunctionModel`
stands in for the model in every role; for the classifier it picks every
domain that holds at least one of the 8 chunks (the rule above).

**Why.** The tests without a key then run the same code as a real model
run: the prompt, the structured output and the citation check. The
domains of this corpus overlap (deploying a service is technical, its
checks are compliance), and routing from the question alone fails where
source boundaries are unclear. Measured here: similarity to domain
descriptions found 12 of 18 expected domains, the search found 18 of 18.
The common practice routes from the question and source descriptions
only; the README says why this design differs and the LLM evals compare
the two.

**Rejected.**
- Search only without a key, the question and the domain descriptions
  only with a key: two code paths, and the tests never run the path a
  real model takes.

### PydanticAI agents in the documented style

**Decision.** Each model role has one module-level PydanticAI `Agent`
without a model; its validators are attached with decorators; the
component passes its injected model, the deps and the timeout at every
run (`agent.run(prompt, model=..., deps=..., timeout=...)`).

**Why.** It is how the PydanticAI documentation shows agents ("instantiate
one agent and use it globally", the model "can also be specified when
running the agent"), so a reviewer who knows the library reads it at once.
The run's own timeout replaces a hand-made one.

**Rejected.**
- An `Agent` built inside every component with its validator attached by
  hand: works, but not the library's style, and it would repeat in the
  classifier and the synthesis.

### Worked examples in the code

**Decision.** The method that runs a module's numbered steps shows, under
each step, what happens to one real eval question (for the domain agent:
Q04, the technical agent). An eval test checks the values in the example.

**Why.** A reader follows real data through the steps instead of
imagining it. The test keeps the comments true; the first example already
found a bug in the offline template ("1." taken as a sentence).
