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

**Decision.** 24 Markdown documents, 8 per domain, 300 to 600 words each,
in `data/<domain>/`. Every document is the expected answer of at least one
eval question.

**Why.** With about 150 chunks, random top-5 retrieval would find the right
document for only about 20% of questions, so retrieval quality can be
measured. 12 documents would give about 37%.

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

**Decision.** The index stores the name of the model that built it; a
query embedded with another model is refused with a clear error.

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
