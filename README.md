# multi-agent-rag

An assistant that answers questions about the internal documentation of
Orla Bank, a fictional bank, by asking three specialised agents and
settling what they disagree on. It is the code part of a two-part
assignment; the other part is the systems design of the bank's workflow
automation platform, [systems_design/self_service_paradox.md](systems_design/self_service_paradox.md).
The documents the assistant searches are that platform's documentation, so
both parts describe one bank.

```bash
uv sync                                   # or: pip install -r requirements.txt
uv run jupyter lab notebooks/demo.ipynb   # the demo; runs without any key
uv run pytest -m "not eval"               # 445 offline tests, about 8 s
```

The committed notebook shows the output of a run with Claude
(`claude-sonnet-5-5`). Without a key it runs on an offline stand-in and
says so. To use a model, copy `.env.example` to `.env` and set
`LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` (or the Azure OpenAI
values).

## The problem

An employee asks: *"What's the process for deploying a new microservice and
what compliance checks are needed?"* The answer is in three places: a
technical guide (how to deploy), a release standard (who approves) and a
compliance checklist (what to check first). The release standard exists in
two versions, and elsewhere in the corpus a runbook says debug logs are kept
30 days while the retention policy says 90. A good answer brings the right
pieces together, uses the version in force, picks the rule that wins and
says where every sentence comes from.

## The idea

```
 question
    |
    v
 classifier ---- reads the 8 closest chunks of the whole corpus,
    |            picks the domains to ask, writes a sub-question for each
    +--------------------+--------------------+
    v                    v                    v
 technical agent     business agent     compliance agent
 (in parallel; each searches only its own documents and writes claims,
  each claim citing the chunks it comes from)
    +--------------------+--------------------+
    v
 conflict check ---- a model finds claims that contradict each other;
    |                code picks the winner by fixed rules
    v
 synthesis --------- a model writes the answer citing [TEC-3] ...;
    |                code checks every cited id and lists the sources
    v
 answer, sources, conflicts, warnings
```

Four principles:

1. **Code coordinates, models read text.** The orchestration is plain Python
   with numbered steps ([rag_system/orchestrator.py](rag_system/orchestrator.py),
   START HERE). A model is used where text must be understood: routing,
   writing claims, spotting a contradiction, writing the answer. The
   orchestrator is still an agent in the assignment's sense: it coordinates
   and synthesises, and the route is a model's decision.
2. **Every sentence has a source.** Agents cite chunk ids; code turns them
   into citations. The synthesis may cite only documents the agents read;
   otherwise PydanticAI sends it back (`ModelRetry`).
3. **Conflicts are settled by rules, not by the model.** A policy outranks a
   standard, a standard a guide, a guide a runbook. Between two documents of
   the same kind, the side that more other documents support wins; if the
   support is equal, the answer shows both and names the owners.
4. **"Nothing relevant" is an answer.** An agent that finds nothing says
   so, and the system does not fill the gap.

The notebook follows the question above through these steps and then asks
"what if the documents disagree, a rule changes, users rate an answer,
nothing answers, a part breaks?".

## How the code is laid out

Each file answers one question and opens with a map of its flow; the entry
method reads as the map's numbered steps, with "Example" comments that
follow one real eval question (a test checks they stay true).

| File | Question it answers |
|---|---|
| `orchestrator.py` | What happens when a question arrives? (START HERE) |
| `query_classifier.py` | Which domains should answer, with which sub-question? |
| `domain_agents.py` | How does one agent answer from its own documents? |
| `conflicts.py` | Which claims contradict each other, and who wins? |
| `vector_store.py` | How are chunks stored, filtered and ranked? |
| `ingestion.py` | How are documents read and cut into chunks? |
| `messages.py` | What do the parts say to each other? (the protocol) |
| `learning.py` | What does feedback change? |
| `monitoring.py` | What is recorded about every answer? |
| `config.py`, `offline_model.py` | Which models run; the stand-in without a key |

The corpus is 26 synthetic Markdown documents with YAML front matter
(`data/`), 300-1,500 words each, 8-9 per domain, written with seven
deliberate contradictions, two superseded versions and two confidential
documents.

## The choices, with their numbers

Every decision, with what was rejected and why, is in
[docs/decisions.md](docs/decisions.md). The ones a reviewer will ask about:

**The classifier searches before the model routes.** The usual practice is
to route from the question plus a description of each source (LlamaIndex
`RouterQueryEngine`). Anthropic's
[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
says routing works "where classification can be handled accurately, either
by an LLM or a more traditional classification model/algorithm"; RealRoute
(arXiv 2604.20860) finds that routing from source descriptions "relies
heavily on the semantic meaning of different data sources, often leading to
routing errors when source boundaries are ambiguous". So the classifier
first retrieves the 8 closest chunks of the whole corpus and the model
routes from that evidence. Measured on the first 12 questions: domain
descriptions found 12 of 18 needed domains, search found 18 of 18. Over all
54 questions the offline rule on the same evidence finds 64 of 64; the cost
is about one extra domain per question.

**Hybrid search.** Embedding similarity (local `potion-base-8M`) and BM25
keyword search, merged by reciprocal rank fusion. On this corpus BM25 alone
is as good as the embeddings (17 vs 16 of 23 documents in the first spike);
the hybrid is never worse than either.

**Each agent keeps the 8 best chunks, plus up to 2 close ones.** First it
kept 3 plus those with similarity of at least 0.4; checking answer facts
showed that the chunk with the fact often ranks 4th to 8th with a
similarity of only 0.30-0.32. Keeping 8 raised the facts that reach the
model from 20 to 22 of 24 at about 40% more text (1,057 to 1,473 words per
question). A chunk that feedback rated not useful loses its guaranteed
place. Anthropic's [Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
found 20 chunks better than 10 or 5.

**Confidence scoring resolves conflicts; it is not a probability.** The
assignment asks for conflict resolution "using confidence scoring". Each
side's score is its kind's rank (policy 4 ... report 0) or, for the same
kind, the number of other documents a judge model finds supporting it. I
did not turn similarity or a model's self-rating into a confidence number:
similarity says a chunk is about the same topic, not that it holds the
answer (for our needed and extra domains the best similarities overlap,
0.44-0.54), and models that state their confidence "tend to be
overconfident" (Xiong et al., arXiv 2306.13063). The answer shows the
winner, the reason ("CMP-3 (policy) overrules TEC-4 (runbook)") and the
overruled claim.

**Old versions are kept, not searched by default.** A document named in
another's `supersedes` is history. A knowledge update is one `store.add()`
of the new version; the classifier's model asks for history when the
question is about the past ("How many approvers did a release need in
2025?" is answered from the 2025 version, and says the 2026 one changed it).

**Learning stays local.** A simulated user rates each source; a rating is
stored with the question it was given for and counts only for questions
with cosine similarity of at least 0.6 to it. A first version kept one
weight per chunk and lost 2 of 13 documents on questions that were never
rated, because one chunk is useful for one question and off-target for
another. Now, after three rounds with 10% wrong ratings: sources from
unexpected documents 210 to 11 on the rated questions, 284 to 182 on their
paraphrases, and no change on questions that were never rated.

**Errors degrade the answer instead of failing it.** An empty question is
refused; after that, a failing step is replaced by a simpler one and named
in `warnings` (classifier fails: ask every domain; detector fails: no
conflict check; synthesis fails: the claims as written). Every model call
has a timeout.

**Models are injected.** One factory per model kind builds the model from
settings (`offline`, `anthropic`, `azure`; embeddings `local`, `azure`);
startup fails loudly if the chosen provider has no key. Clock and random
seeds also enter through constructors, so tests never patch.

## Evidence

The gold set ([tests/evals/questions.yaml](tests/evals/questions.yaml))
has 54 questions with expected domains, documents and answer facts. On 19
of them I tuned the thresholds. The other 35 are held out: other models
wrote them from the document titles alone, after the tuning, and each batch
ran once with the thresholds frozen.

Offline (no model; `tests/evals/`, always run):

| measure | tuning (19) | held-out (35) |
|---|---|---|
| classifier finds the expected domains | 26 of 26 | 38 of 38 |
| expected document in its domain's top 5 | 91% | 68% |
| mean reciprocal rank (random order: 0.34) | 0.75 | 0.59 |
| expected facts in the chunks the agents keep | 92% | 65% |

With `claude-sonnet-5-5` (`tests/evals/test_llm.py`, `uv run pytest -m eval`
with a key, about 6 minutes; a judge model reads the answers):

| measure | tuning | held-out | common target |
|---|---|---|---|
| facts in the chunks the model read (context recall) | 92% | 68-70% | 75-80% |
| facts stated in the answer | 88% | 73-76% | |
| answer statements supported by the sources (faithfulness) | 97% (691 of 710) | | 90-95% in regulated work |
| questions no document answers that end in "nothing relevant" | | 6 of 7 | |
| conflicts found and decided as expected | 3 to 5 of 5 per run | | |

The targets are practitioner guidance, not a standard
([premai](https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026));
scores depend on the judge and compare only within one system.

What the numbers say:

- **The answers stick to their sources.** 97% of the statements are
  supported, and 6 of 7 out-of-scope questions (meeting rooms, travel
  expenses, a laptop licence, ...) end in "The documentation holds nothing
  that answers this question."
- **Retrieval is the limit on new wording.** On held-out questions the
  chunk with the answer often ranks below the first 8 of its domain (22nd,
  31st, 18th in three cases I looked at). The model's rewritten
  sub-questions barely help (26 vs 24 of 37 facts). Two things I tried did
  not help: `potion-retrieval-32M` (same facts, mean reciprocal rank 0.79
  vs 0.75, every threshold to re-tune) and a local cross-encoder reranker
  (`ms-marco-MiniLM-L-6-v2`, `bge-reranker-base`: held-out facts unchanged,
  6 of 9). The next step is a stronger embedding model, which production
  would have anyway (Azure OpenAI embeddings).
- **Faults found.** In Q25 the model invented a 90-day limit for copies of
  ID documents (two runs of two). In one run of Q30 the detector paired two
  rules that do not contradict (one is stricter than the other), and the
  rules then dropped the stricter one. In Q24 (bonuses to Payroll) the
  agents answered from nearby chunks, though the answer said the sources do
  not confirm it.

Limits of the evidence: 54 questions and a few runs show where the problems
are, not precise rates; the judge is the same model that answers; I chose
the expected facts, and an answer can be right while missing my phrase; the
learning table's first row is circular (the simulated user rates by the same
expected documents it counts).

## Production on-premise with Azure OpenAI

The target from the assignment's authors: models on Azure OpenAI,
everything else on-premise.

- **Models:** `LLM_PROVIDER=azure` and `EMBEDDING_PROVIDER=azure` build
  PydanticAI's Azure model and an Azure embedding client from the
  deployment names. The configuration is unit-tested; **the Azure path has
  not been run against Azure** (no quota on the trial account).
- **Vector store:** the demo keeps the index in memory and rebuilds it at
  start (about 170 chunks, under a second). For production I would use
  pgvector: the class and domain filters are one SQL `WHERE`, documents,
  metadata and vectors change in one transaction, and it is a database to
  run, not a new kind of system. It would also store the embedding model next to the vectors and
  refuse a query embedded by another model. It is one class behind the same
  `add` / `search` interface; it is not implemented here.
- **Monitoring:** `monitoring.py` keeps records in memory for the notebook;
  production would send the same records to OpenTelemetry, which PydanticAI
  already uses for model calls.
- **Data rules:** the confidential documents are filtered by the caller's
  clearance before ranking; what may be sent to the cloud model is a
  question for the bank (below).

## Assumptions and questions I would ask the business

| What was unclear | What I assumed | Alternative I considered |
|---|---|---|
| Which document wins when two disagree? | Kind first (policy, standard, guide, runbook), then support by other documents; never the newest alone (in 3 of our conflicts the weaker document is the newer one) | Newest wins; the model decides |
| Who settles a contradiction nobody can decide? | The answer names both owners and stops | Escalate to a fixed role |
| Who may see what? | Three classes (public, internal, confidential); the caller's clearance filters the search | Per-department access lists |
| May document text go to Azure OpenAI? | Yes for internal documents. The two confidential ones go to the model too when the caller has confidential clearance, which the bank's own rule in the corpus (CMP-2) allows only with pseudonymisation and a sign-off | Keep confidential text on-premise and answer it with a local model |
| What is a successful answer? | It cites at least one source and no agent failed | Rated useful by the asker |
| Should old rules be answerable? | Yes, when the question asks about the past | Delete superseded versions |
| Where does feedback come from? | Simulated: a user rating each source | Thumbs up or down on the whole answer |

## Known gaps

- Retrieval on unfamiliar wording (above); offline, the 0.4 bar does not
  stop the 7 out-of-scope questions.
- The offline stand-in writes templated answers and finds no conflicts; it
  exists so the notebook and tests run without a key, and design choices
  were judged in model mode.
- Conflict detection varies between runs (Q08 and Q15 each missed once in
  four runs); the faults above.
- Not run against Azure; not tested yet on Python 3.12 and 3.14.

## How this was built

I worked with Claude Code as a coding agent: I made the design decisions,
the agent implemented them test-first, and the decisions are recorded with
their rejected options in [docs/decisions.md](docs/decisions.md) and as
standing rules in [CLAUDE.md](CLAUDE.md).
