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

**Why.** The assignment already links them: Task B lets employees "build their
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

**Decision.** Seven contradictions are written into the corpus:

| # | Documents | Kind | Settled by |
|---|---|---|---|
| 1 | TEC-2 vs TEC-3 | an older and a newer version | metadata (`supersedes`) |
| 2 | BUS-1 vs BUS-2 | an older and a newer version | metadata (`supersedes`) |
| 3 | TEC-4 vs CMP-3 | a runbook vs a policy | kind |
| 4 | BUS-4 vs BUS-3 | a guide vs a policy | kind |
| 5 | TEC-5 vs BUS-3 | a guide vs a policy | kind |
| 6 | BUS-4 vs BUS-7 | two guides | evidence (TEC-3 refers rollbacks to BUS-7) |
| 7 | BUS-6 vs CMP-7 | two standards | no winner (no other document takes a side) |

Conflicts 6 and 7 were added in Phase 3, with eval questions Q15 and Q16,
so that both outcomes of the same-kind rule (see "Conflicts are resolved
by confidence scores") run on real documents.

In conflicts 3 and 4 the weaker document is the newer one, so recency alone
picks the wrong answer.

Conflicts 1 and 2 are settled by metadata: the newer version names the
older one in `supersedes`, and search leaves superseded versions out
unless a question asks about history. The conflict rules deal with
conflicts 3 to 7, where nothing in the metadata links the documents.

**Why.** The assignment asks to "handle contradictory information from different
sources". A conflict inside one domain reaches one agent; a conflict across
domains only becomes visible when the orchestrator combines the agents'
answers, so both kinds are needed.

**Rejected.**
- Version conflicts only: they do not involve "different sources".
- A conflict with no winner, shown to the user as is: its rule belongs
  with the conflict resolution rules and can be added there (it was, in
  Phase 3, as conflict 7).

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
`classification`, `owner`. (`status` was removed in Phase 3; see "A new
version takes effect when it is added".)

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

**Why.** The reviewer finds the files the assignment names where the assignment
puts them.

**Rejected.**
- A `src/` or per-component layout: the assignment would have to be mapped onto
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
assignment's definition: it "coordinates multiple agents and synthesizes their
responses". This is the routing and parallelization pattern described in
Anthropic's ["Building effective agents"](https://www.anthropic.com/research/building-effective-agents).

**Rejected.**
- An LLM orchestrator that calls the domain agents as tools: the route
  differs from run to run, cannot be shown honestly offline, and makes the
  classifier the assignment asks for redundant.
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
`failed`), a list of claims and a confidence (renamed `best_similarity` in
Phase 3; see "No confidence level for the whole answer"). A claim is one statement
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
- BM25 only: no vector store, which the assignment asks for.

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

Every output gets a name (`ToolOutput(Plan, name="plan")`), and the offline
`FunctionModel` picks its template by that name. The tests block requests
to real models (`ALLOW_MODEL_REQUESTS = False`).

**Why.** It is how the PydanticAI documentation shows agents ("instantiate
one agent and use it globally", the model "can also be specified when
running the agent"), so a reviewer who knows the library reads it at once.
The run's own timeout replaces a hand-made one. The output name is what
the real model sees as the tool to call; without it the offline model had
to rely on the class name pydantic writes into the JSON schema. The testing
guide recommends blocking real requests "to block any requests from being
made to non-test models accidentally".

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

### The classifier ranks by meaning only

**Decision.** The classifier's search over the whole corpus orders chunks
by embedding similarity only; the domain agents keep hybrid search. The
store's `search` takes the ranking as a parameter (hybrid by default).

**Why.** The rule for choosing domains was measured with this ranking. On
the 14 eval questions it finds all 20 expected domains with 8 extra ones;
hybrid ranking finds the same 20 with 14 extra, and 10 of those extra
agents answer, which adds noise to the answer and, with a model, costs one
model call each.

**Rejected.**
- Hybrid ranking for the classifier too: one search method, but 6 more
  extra agents on 14 questions.

## Advanced features

### Conflicts are resolved by confidence scores

**Decision.** Each side of a conflict gets a confidence score; the higher
score wins.
1. Different `kind`: the score is the kind's rank (policy 4, standard 3,
   guide 2, runbook 1, report 0). A report holds facts, not rules.
2. Same `kind`: the score is the number of other documents that support
   the claim. For each side, the store is searched with the claim's text
   over all domains, with the caller's clearance; the two disputing
   documents are left out of the results. A judge model labels each found
   chunk "supports A", "supports B" or "neither", and code counts
   supporting documents, not chunks.
3. A difference of at least one wins. Equal scores mean no winner: the
   answer shows both claims and names both documents' owners.

The answer states the winner and the reason, for example "CMP-3 (policy)
overrules TEC-4 (runbook)" or "TEC-3 refers rollbacks to BUS-7".

**Why.** The assignment asks to "handle contradictory information from different
sources using confidence scoring". With the kind hidden, the three
authority conflicts test each candidate signal: the later date is right in
1 of 3; how directly each side is worded is equal in all three; the
evidence count is right in 2 and equal in 1, never wrong. Between kinds,
a bank's hierarchy applies (a runbook cannot overrule a policy), the way
law puts a higher rule before a later one.

**Rejected.**
- The later date first, then the kind: 1 of 3 right; in conflicts 3 and 4
  the weaker document is the newer one.
- The model decides with no fixed rule: not repeatable, and an audit
  cannot check why a side won.
- A score from how directly each side is worded: equal in all three
  conflicts, so the winner would be chance.
- A weighted sum of date, wording and evidence: invented weights that
  three conflicts cannot calibrate.
- Retrieval similarity as a tie-breaker: it measures how close a text is
  to the question, not whether it is right.

### One conflict check, in the orchestrator

**Decision.** A new step between the agents' answers and the synthesis:
a detector model receives every claim with its document, kind and date and
returns the pairs that contradict; `conflicts.py` scores each pair and the
synthesis receives the winner and the reason. The agents' instructions say
to write two disagreeing chunks as two separate claims.

**Why.** All claims reach the orchestrator, including both sides of a
conflict inside one domain (Q07 brings BUS-4 and BUS-3 from the business
agent), so one place sees every conflict.

**Rejected.**
- A check in each agent and another in the orchestrator: the same job
  twice, up to four more model calls per question, nothing found that one
  check misses.
- Leaving it to the synthesis: the model would pick the winner, and a test
  could only read the text.

### Offline, conflicts are not detected

**Decision.** The offline stand-in finds no conflicts and says so in its
note; the answer shows both claims. The scoring rule is tested with the
pair given; detection is checked by the LLM evals.

**Why.** The best heuristic measured (similar claims with different numbers
or a one-sided negation) finds the right pair in 1 of 3 conflicts and flags
50 false pairs on 16 questions; each false pair would drop a true claim.

**Rejected.**
- That heuristic: 1 of 3, 50 false conflicts.
- A list of known conflicts: a lookup written for our questions, blind to
  any new document.

### No confidence level for the whole answer

**Decision.** The final answer carries the scores and reasons of its
conflicts, not a separate confidence level. The agent's number is renamed
from `confidence` to `best_similarity`: it decides "nothing relevant" and
is shown by monitoring.

**Why.** The assignment ties confidence scoring to conflicts. Retrieval
similarity is not confidence: needed and extra domains overlap between
0.44 and 0.54 here, and others report the same
([answerable and unanswerable questions "overlap from 0.31 to 0.59"](https://dev.to/klausbyskov/retrieval-confidence-cant-tell-your-rag-chatbot-when-the-answer-is-missing-2ml0)).
A model's own rating is no better: "LLMs, when verbalizing their
confidence, tend to be overconfident"
([Xiong et al.](https://arxiv.org/abs/2306.13063)).

**Rejected.**
- A level (high, medium, low) for each answer: the assignment does not ask for
  it, and a failed agent is already visible in the answer.
- A number from a formula over similarity and kind: invented weights.
- The model rating itself: measured overconfident in the literature.

### Learning: feedback is kept with its question

**Decision.** A simulated user rates every cited source as useful (its
document is an expected answer in the gold set) or not, and is wrong 10%
of the time (`random.Random(42)`). Each rating is kept with the question it
was given for. For a new question, a rating counts only if that question is
close in meaning to the rated one (cosine at least 0.6); each counting
rating multiplies the chunk's weight by 1.25 (useful) or 0.8 (not useful),
within 0.5 to 2. The agent's search uses the weight in the order and in the
0.4 bar. Weights never move a conflict winner. The notebook shows the gold
set before and after three rounds, on the same questions, on their
paraphrases (`paraphrase` in `questions.yaml`) and on questions that
received no feedback, plus one question in detail.

**Why.** A chunk can be useful for one question and beside the point for
another: TEC-6#5 ("log retention follows CMP-3") is an expected answer for
Q02 and off-target for Q06. A weight per chunk, measured end to end, lost
2 of 13 expected documents on questions that received no feedback. Kept
with its question, feedback changes nothing on those questions (13 of 13,
34 off-target sources before and after), cuts off-target sources on the
same questions from 105 to 28 and on their paraphrases from 189 to 143,
and loses no expected document. [FLAIR](https://arxiv.org/html/2508.13390)
stores feedback the same way, as (query, document, signal) with the query
embedding, and ignores feedback from queries below a similarity threshold.

**Rejected.**
- A weight per chunk: one question's rating changes unrelated questions
  (2 of 13 expected documents lost).
- Counting only useful ratings: off-target sources double (105 to 207),
  because a raised chunk enters every question.
- A weight per document: feedback about one section would also move the
  document's other sections.
- Learning each domain's similarity bar: on questions without feedback it
  finds 9 of 13 documents instead of 13.
- Learning how many chunks a domain needs to be asked: one fewer extra
  agent on 8 questions, and the learned value applies to every question.

The 0.6 threshold was tuned on these 16 questions (0.7 gives about the
same); the Phase 4 gold set checks it.

### A new version takes effect when it is added

**Decision.** The store derives whether a document is in force from the
`supersedes` links: a document that another held document supersedes is
history. The `status` field leaves the metadata. A knowledge update is one
`store.add()`.

**Why.** "TEC-3 replaces TEC-2" was written in two files. A new version
added at run time would leave the old file saying "current", and both
versions would answer.

**Rejected.**
- `add()` changes the old document's status in memory: after a restart
  the old file says "current" again.
- The new version deletes the old one: no history, no audit.

### Who asks for old versions

**Decision.** Each sub-query in the plan has `include_history`; the
classifier's model sets it when the question asks about the past or an
old version, and the agent passes it to the search. Offline it is always
false.

**Why.** Recognising that a question is about the past is language
understanding. One of the 16 questions needs it (Q13, "in 2025").

**Rejected.**
- Keywords in code: "in 2026" would switch history on without need, and
  "before the new standard" would not.
- Always searching old versions: outdated rules take result slots.

### Monitoring

**Decision.** `monitoring.py` keeps one record per question in memory: per
agent the status, duration, chunks kept, best similarity and error; per
question the total duration, the conflicts (decided, no winner) and the
embedding model. A question is successful when its answer cites at least
one source and no agent failed, partial when it has an answer but an agent
failed, failed otherwise. The summary gives the success rate and, per
agent, the share of each status, the mean duration and the share of
sources rated useful. The clock is injected.

**Why.** "Query success" is a notion of this system, so it is defined and
tested here. Production would send the same records to OpenTelemetry,
which PydanticAI already uses for model calls.

**Rejected.**
- PydanticAI's instrumentation alone: needs a backend to view, and has no
  notion of a successful question.
- Records in a file or SQLite: more code that the demo does not need.

### Errors

**Decision.**
1. A question with no word is refused before the search
   (`ValueError("the question is empty")`).
2. A plan may name no domain; the answer is then "nothing that answers"
   and no agent is called.
3. A failure after the agents keeps the answer and adds a warning: the
   classifier fails, so all three domains are asked; the detector fails,
   so conflicts are not checked; the judge fails, so the conflict has no
   winner; the synthesis fails, so code lists the claims with their
   citations.
4. Monitoring counts such a question as partial.
5. Every model run (classifier, agents, detector, judge, synthesis) has a
   timeout, 30 s by default, set once on the orchestrator; a run past it
   is a failure of that step, handled as above.

**Why.** Today an empty question crashes (`Plan` needs a domain), and any
model failure outside the agents escapes `answer()`. The agents' claims
are valid even when a later step fails, so the user should get them.
Network errors and rate limits are already retried by the provider SDKs;
a model that hangs without an error would otherwise hold the answer.

**Rejected.**
- One error naming the failed step: the user loses valid claims when only
  the synthesis failed.
- Our own retries with backoff: the SDKs already retry, and a real outage
  still ends in an error.


## Task B: the self-service platform

The design starts from research (sources in
`systems_design/self_service_paradox.md`), not from the Task A corpus;
the two documents were checked against each other at the end.

### The setting

**Decision.** A bank, described by four conditions at the top of the
document: regulated, so every run is audited; some core systems have no
API; language models run in Azure and everything else on-premise; personal
data of customers must not leave the bank unprotected. The document does
not refer to Task A documents.

**Why.** The conditions turn the trade-offs into concrete ones (the assignment
evaluates "trade-offs and constraints" and "feasibility").

**Rejected.**
- A generic company: the trade-offs stay words, and the two tasks tell two
  stories.
- The bank plus references to Task A documents: a reader of Task B would
  need the corpus.

### Two roles

**Decision.** The assignment's two roles. Business users work in the wizard and
on the canvas (the more experienced ones assemble workflows and write
templates for colleagues); power users write code and blocks and use the
API. The platform team owns the catalog, the rules and the engine and is
not a user role.

**Why.** The assignment's business users already ask for "drag-and-drop
simplicity", which is the canvas, so two roles cover all views.

**Rejected.** Three roles with a process analyst: a role the assignment does not
ask for; the evidence for it (Microsoft's third persona) turned out to be
IT/DevOps, not an analyst.

### One definition, many views

**Decision.** A workflow is one declarative definition (YAML) that every
view edits. Free code lives only in local code steps, shown on the canvas
as closed boxes (name, input, output, owner). The platform validates every
save. A workflow that leaves its template's shape is edited on the canvas.

**Why.** Every view edits the same structure, so nothing is lost when a
workflow moves between the canvas and code (AWS Step Functions works the
same way).

**Rejected.**
- The definition is a program and the canvas only draws it: business users
  cannot edit power users' workflows, two classes of workflows.
- Two-way translation between the canvas and arbitrary code: unsolved in
  general; generated code is either edited and breaks the translation, or
  left alone.

### The SDK is one more view

**Decision.** The stored definition is the only source. SDKs in several
languages load it, change it and save it with a version check (a save based
on an old version is refused). A script may generate the first version.
Repetition and branching are built-in steps of the format, so rules such as
"one step per branch of the bank" survive edits.

**Why.** Everyone can edit every workflow, and power users keep their own
language and editor (the developer's proposal).

**Rejected.**
- Workflows managed in code (Git) with a read-only canvas: two modes of
  ownership; business users locked out.
- No SDK: "full coding flexibility" only half covered.

### The format

**Decision.** A subset of the Open Workflow specification (task kinds `do`,
`call`, `switch`, `for`, `wait`, `run`, `try`) plus the platform's own fields in its
`metadata`; other task kinds are refused on save.

**Why.** No invented language; the schema and SDKs in several languages
exist.

**Rejected.**
- A new minimal YAML format: the schema and every SDK would have to be
  written.
- BPMN 2.0: XML instead of YAML, and it needs its own editor.

### Assembled from small parts

**Decision.** The platform is assembled from small libraries (a durable
execution library over Postgres, a canvas library, forms generated from
JSON Schema, a code editor, an expression language, a policy engine) plus
an in-house interpreter, catalog and rules. The document has a "ready-made
or built in-house"
table.

**Why.** The controls the bank needs most (trust levels, data classes,
review by risk) are missing or paid in the complete platforms, so they are
built either way, better over parts that can be replaced one at a time.

**Rejected.**
- A complete platform (Kestra, Camunda 8) plus the bank's own rules: heavy, key
  features paid, the rules forced into a foreign model.
- Everything ourselves, including the engine: not realistic for a bank.

### How a block runs

**Decision.** A catalog block is either declarative (a description of a
call to an existing API; the engine makes the call) or a worker in any
language that takes tasks from the engine's queue.

**Why.** Most blocks wrap existing APIs and need no code; the assignment names no
language; a worker that fails cannot bring the platform down.

**Rejected.**
- Workers only: a program just to forward a request.
- Plugins inside the platform: one language; a faulty block brings down or
  exposes the whole platform.

### Local code

**Decision.** Local code inside one workflow is allowed. It runs in its own
container with limits and no direct network, reaches other systems only
through catalog blocks, and declares input and output like a block.

**Why.** "Custom logic" from the assignment without the procedure for a new
block; isolation protects the bank.

**Rejected.**
- No local code, every piece of code a catalog block: ten lines need a
  block, a worker and a registration.
- Local code inside the engine: it gets the engine's access to all
  workflows and data.

### Trust levels

**Decision.** Three levels for blocks and templates: certified (everyone,
production), team (the author team, production in its own workflows),
experimental (the author team, never production). Promotion by a platform
team review. Business users see certified blocks only.

**Why.** Business users see only what was checked; teams can try things
without waiting. The names match the Task A corpus.

**Rejected.**
- Two levels: teams either wait for approval or use unapproved blocks in
  production.
- No levels, owners only: business users cannot tell tested from untested.

### Data classes along the data path

**Decision.** Every block declares the class of data it returns and the
highest class it accepts (public, internal, confidential; customer data is
confidential, as in the Task A corpus). On save the platform follows each
output to its inputs and refuses confidential data reaching a block that
accepts less, suggesting a masking step; the check runs again at run time.

**Why.** The error is caught on the canvas, at save, not in production and
not by someone who has to remember.

**Rejected.**
- Groups of blocks as in Power Platform: too coarse, a workflow that reads
  the CRM could send no email at all.
- No automatic check, the review catches it: relies on memory.
- A fourth class "personal": the Task A corpus would have to change a day
  before the deadline.

### Review by risk

**Decision.** A change is high risk when it touches confidential data,
adds the first AI step to a workflow, adds a block for a new system, moves
money or adds local code. High risk needs approval by a second person who
is not the author; everything else goes live after the automatic checks.
The list joins the first version of this rule with the Task A four-eyes policy.

**Why.** Review where there is something to lose ("risk-based
guardrails", Gartner 2026).

**Rejected.**
- Review of every production release: people bypass the platform.
- No human review: local code that moves money would go live unchecked.
- The first version of the rule only: two documents with two rules for one bank.

### AI

**Decision.** AI writes drafts of definitions (validated, reviewed on the
canvas, published the normal way) and runs as blocks with fixed input and
output under the data rules. No autonomous agents in the first version.

**Why.** AI lowers the floor further, and a predefined path stays
predictable and auditable.

**Rejected.**
- Agents now: the path is decided at run time, so audit is hard.
- AI blocks only: misses the largest help for business users.

### Versions

**Decision.** A run finishes on the version it started with; rollback makes
the previous version active. Blocks use semantic versioning: minor changes
reach every workflow, a breaking change is a new major version that
workflows adopt when their owners move; the catalog shows which workflows
use which version.

**Rejected.**
- Always the latest version: one breaking change stops every workflow that
  uses the block.
- Exact versions everywhere: bug fixes reach no one.

### Migration

**Decision.** Wrap first, take apart later (strangler fig): every existing
automation enters as one worker block in a one-step workflow and gets an
owner, a schedule and audit at once; the riskiest are split into steps
first.

**Rejected.**
- Rewrite from zero: months without audit.
- New automations only: two worlds for good.

### The shape of the document

**Decision.** First a short story: each problem and the idea that solves
it, in plain words with two small diagrams. Then the details: what a
definition looks like and who edits what (the business user and the
developer on one workflow), a glossary, how the pieces fit, a decision tree
that sends seven bank use cases to their path (the assignment asks for
"practical and implementable solutions"), and "Why this design" (the
problem, what "one platform" means, the principles). Then the assignment's
four sections with their own names, trade-offs and the questions for the
business. Diagrams in Mermaid, which GitHub draws and a model reads as
text; details folded.

**Rejected.**
- Ordered by decisions: the reviewer has to find the four sections; this
  file already has the decisions.
- A short document of about 1,500 words: the assignment asks for a
  "comprehensive solution".
- ASCII diagrams only: heavier to read; the first draft read like a
  reference and was rewritten.
