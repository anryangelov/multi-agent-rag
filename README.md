# multi-agent-rag

An assistant for the employees of Orla Bank, a fictional bank. It answers
questions about the bank's workflow automation platform from the platform's
internal documentation: three departments' documents, some of them old
versions, some contradicting each other. Three agents search in parallel,
code settles what they disagree on, and every sentence of the answer names
its source.

This is the code half of a two-part assignment. The other half designs the
platform these documents describe:
[systems_design/self_service_paradox.md](systems_design/self_service_paradox.md).

```bash
uv sync                                   # or: pip install -r requirements.txt
uv run jupyter lab notebooks/demo.ipynb   # the demo, runs without any key
uv run pytest -m "not eval"               # 445 offline tests, about 8 s
```

## What it does

An employee asks: **"How long can we keep the troubleshooting logs of an
API?"** The troubleshooting runbook says 30 days. The data retention policy
says 90. This is the answer Claude wrote (from
[the notebook](notebooks/demo.ipynb), shortened):

> Troubleshooting logs of an API, including debug logs, can be kept for 90
> days and are then deleted [CMP-3]. ...
>
> **Settled conflict:** One claim said debug logs turned on for
> troubleshooting an API are kept for 30 days and then deleted [TEC-4]. It
> is overruled. The policy (CMP-3) takes precedence over the runbook
> (TEC-4), so the 90-day period applies [CMP-3].
>
> **Conditions for handling the logs:**
> - Debug logging for the API should be turned on for at most 24 hours [TEC-4]. ...
> - Personal data must be masked before it is written to any log, including at debug level [CMP-5].
>
> Sources: [CMP-3] Data Retention Policy, v1, 2025-06-01, "Retention periods"; [TEC-4] API Performance Troubleshooting Runbook, v1, 2026-05-20, "Step 4: debug logging"; ...

The answer does not pick the newer document (the runbook is newer). It
picks the stronger one, says so, and shows what it overruled.

## The idea

```
 question
    |
    v
 classifier ---- reads the 8 closest chunks of the whole corpus,
    |            picks the departments to ask, writes a sub-question for each
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
 synthesis --------- a model writes the answer citing [CMP-3] ...;
    |                code checks every cited id and lists the sources
    v
 answer, sources, conflicts, warnings
```

Four principles:

1. **Code coordinates, models read text.** The steps above are plain Python
   ([rag_system/orchestrator.py](rag_system/orchestrator.py), START HERE).
   A model is used only where text must be understood.
2. **Every sentence has a source.** The answer may cite only documents the
   agents read; otherwise the model is asked again.
3. **Conflicts are settled by rules, not by the model.** A policy outranks a
   standard, a standard a guide, a guide a runbook.
4. **"Nothing relevant" is an answer.** The system does not fill a gap with
   what the documents do not say.

## How the answer above came about

1. **The classifier** searched the whole corpus, saw chunks from technical
   and compliance documents, and asked those two agents. For compliance it
   sharpened the question on its own: *"What does the Data Retention Policy
   say about log retention?"*
2. **The two agents**, in parallel, each searched only their own documents
   and wrote short claims. The technical agent wrote *"Debug logs ... are
   kept for 30 days"* citing the runbook; the compliance agent wrote *"API
   request logs, including debug logs, are kept for 90 days"* citing the
   policy. They never talk to each other.
3. **The conflict check**: a model saw that the two claims cannot both be
   true. Code then applied the rule: a policy (rank 4) outranks a runbook
   (rank 1). Had both been policies, the side that more other documents
   support would have won, or, with equal support, the answer would have
   shown both and named the owners who must decide.
4. **The synthesis**: a model wrote the answer with the winner, the reason
   and the overruled claim, citing document ids. Code checked every id and
   built the source list itself.

The [notebook](notebooks/demo.ipynb) follows the assignment's first
scenario the same way, then asks: what if the documents disagree, a rule
changes tomorrow, users say an answer was not useful, no document answers,
a part breaks?

## What I learned by measuring

I wrote a gold set of 54 questions with the departments, documents and
facts a right answer needs. I tuned the thresholds on 19 of them. The
other 35 were written later by other models that saw only the document
titles, and I ran each batch once without changing anything.

**The rule for how much text the agents read was dropping the answer.**
Agents first kept the 3 best chunks plus any with a similarity of at least
0.4. Checking whether the answer's facts reached the model showed that the
chunk with the fact often ranked 4th to 8th with a similarity of only about 0.3.
Keeping the 8 best raised the facts that reach the model from 20 to 22 of
24, for about 40% more text.

**On new questions retrieval is the weak part.** The expected document is
in its department's top 5 for 91% of the tuning questions and 68% of the
held-out ones; the facts that reach the model fall from 92% to about 68%,
below the 75-80% practitioners aim for. The fix above did not help there:
on new wording the chunk with the answer ranks 18th to 31st. A larger local
embedding model and a reranker did not help either. The limit is the small
local embedding model I chose so the demo runs without a key; production
would use Azure OpenAI embeddings.

**The model sticks to its sources.** A judge model checked every statement
of every answer against the chunks the agents read: 97% are supported (691
of 710; the bar for regulated work is about 90-95%). 6 of 7 questions no
document answers (meeting rooms, travel expenses, a laptop licence, ...)
end in *"The documentation holds nothing that answers this question."* One
real invention: for copies of customer ID documents the model gave a
90-day limit that no document sets.

**Learning had to stay local.** A rating of a source first changed that
chunk for every question, and unrelated questions lost 2 of 13 expected
documents. Now a rating counts only for questions close in meaning to the
one it was given for: after three rounds of simulated feedback, sources
from unexpected documents fall from 210 to 11, and questions that were
never rated do not change.

## How this was built

I worked with Claude Code as a coding agent: I made the design decisions,
the agent implemented them test-first, and every decision is recorded with
the options it rejected in [docs/decisions.md](docs/decisions.md) and as
standing rules in [CLAUDE.md](CLAUDE.md).

---

The rest is reference.

<details>
<summary><b>Running with a model</b></summary>

Copy `.env.example` to `.env` and set `LLM_PROVIDER=anthropic` and
`ANTHROPIC_API_KEY`, or the Azure OpenAI values (`LLM_PROVIDER=azure`,
key, endpoint, API version, deployment names). Startup fails with the
names of the missing variables if the chosen provider is not complete.
Without `.env` everything runs on an offline stand-in that composes
answers from the retrieved chunks by template and finds no conflicts; the
notebook says which mode it ran in. The committed notebook carries the
output of a run with `claude-sonnet-5-5`.

`uv run pytest -m eval` runs the LLM evals (about 6 minutes, needs a key).

</details>

<details>
<summary><b>How the code is laid out</b></summary>

Each file answers one question and opens with a map of its flow. The entry
method reads as the map's numbered steps, with "Example" comments that
follow one real eval question; a test checks they stay true.

| File | Question it answers |
|---|---|
| `orchestrator.py` | What happens when a question arrives? (START HERE) |
| `query_classifier.py` | Which departments should answer, with which sub-question? |
| `domain_agents.py` | How does one agent answer from its own documents? |
| `conflicts.py` | Which claims contradict each other, and who wins? |
| `vector_store.py` | How are chunks stored, filtered and ranked? |
| `ingestion.py` | How are documents read and cut into chunks? |
| `messages.py` | What do the parts say to each other? (the protocol) |
| `learning.py` | What does feedback change? |
| `monitoring.py` | What is recorded about every answer? |
| `config.py`, `offline_model.py` | Which models run; the stand-in without a key |

The corpus (`data/`) is 26 synthetic Markdown documents with YAML front
matter, 8-9 per department, with seven deliberate contradictions, two
superseded versions and two confidential documents. Tests: `tests/unit/`
for each part, `tests/test_scenarios.py` for the assignment's three
questions end to end, `tests/evals/` for the gold set.

</details>

<details>
<summary><b>The design choices, with their numbers</b></summary>

Every decision, with the options rejected, is in
[docs/decisions.md](docs/decisions.md).

**The classifier searches before the model routes.** The usual practice is
to route from the question plus a description of each source (LlamaIndex
`RouterQueryEngine`). Anthropic's
[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
says routing works "where classification can be handled accurately, either
by an LLM or a more traditional classification model/algorithm"; RealRoute
(arXiv 2604.20860) finds that routing from source descriptions "relies
heavily on the semantic meaning of different data sources, often leading to
routing errors when source boundaries are ambiguous". On the first 12
questions, descriptions found 12 of 18 needed departments, search 18 of 18.
Over all 54 questions the offline rule on the same evidence finds 64 of 64;
the cost is about one extra department per question.

**Hybrid search.** Embedding similarity (local `potion-base-8M`) and BM25
keyword search, merged by reciprocal rank fusion. On this corpus BM25
alone is as good as the embeddings (17 vs 16 of 23 documents in the first
spike); the hybrid was never worse than either.

**Each agent keeps the 8 best chunks, plus up to 2 close ones** (at least
0.4 similarity). A chunk that feedback rated not useful loses its
guaranteed place. Anthropic's
[Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
found 20 chunks better than 10 or 5.

**Confidence scoring resolves conflicts; it is not a probability.** The
assignment asks for conflict resolution "using confidence scoring". Each
side's score is its kind's rank (policy 4, standard 3, guide 2, runbook 1,
report 0) or, for the same kind, the number of other documents a judge
model finds supporting it. I did not turn similarity or a model's
self-rating into a confidence number: similarity says a chunk is about the
same topic, not that it holds the answer (the best similarities of needed
and extra departments overlap, 0.44-0.54), and models that state their
confidence "tend to be overconfident" (Xiong et al., arXiv 2306.13063).

**Old versions are kept, not searched by default.** A document named in
another's `supersedes` is history. A knowledge update is one `store.add()`
of the new version. The classifier's model asks for history when the
question is about the past: "How many approvers did a release need in
2025?" is answered from the 2025 version.

**Learning stays local.** A rating is stored with its question and counts
only for questions with cosine similarity of at least 0.6 to it; a useful
rating multiplies the chunk's weight by 1.25, a not useful one by 0.8.

**Errors degrade the answer instead of failing it.** An empty question is
refused. After that a failing step is replaced by a simpler one and named
in `warnings`: classifier fails, every department is asked; detector fails,
no conflict check; synthesis fails, the claims as written. Every model call
has a timeout.

**Models are injected.** One factory per model kind builds the model from
settings; clock and random seeds also enter through constructors, so tests
never patch.

</details>

<details>
<summary><b>Evaluation numbers</b></summary>

Gold set: [tests/evals/questions.yaml](tests/evals/questions.yaml), 19
tuning and 35 held-out questions.

Offline (`tests/evals/`, always run):

| measure | tuning (19) | held-out (35) |
|---|---|---|
| classifier finds the expected departments | 26 of 26 | 38 of 38 |
| expected document in its department's top 5 | 91% | 68% |
| mean reciprocal rank (random order: 0.34) | 0.75 | 0.59 |
| expected facts in the chunks the agents keep | 92% | 65% |

With `claude-sonnet-5-5` (`tests/evals/test_llm.py`; judge models read the
answers):

| measure | tuning | held-out | common target |
|---|---|---|---|
| facts in the chunks the model read (context recall) | 92% | 68-70% | 75-80% |
| facts stated in the answer | 88% | 73-76% | |
| statements supported by the sources (faithfulness) | 97% (691 of 710) | | 90-95% in regulated work |
| out-of-scope questions ending in "nothing relevant" | | 6 of 7 | |
| conflicts found and decided as expected | 3 to 5 of 5 per run | | |

The targets are practitioner guidance, not a standard
([premai](https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026)).

Tried and rejected for retrieval on new wording: `potion-retrieval-32M`
(same facts, mean reciprocal rank 0.79 vs 0.75, every threshold to
re-tune) and a local cross-encoder reranker (`ms-marco-MiniLM-L-6-v2`,
`bge-reranker-base`: held-out facts unchanged, 6 of 9).

Faults found: in Q25 the model invented a 90-day limit for copies of ID
documents (two runs of two). In one run of Q30 the detector paired two rules
that do not contradict (one is stricter), and the rules dropped the stricter
one. In Q24 (bonuses to Payroll) the agents answered from nearby chunks,
though the answer said the sources do not confirm it.

Limits of the evidence: 54 questions and a few runs show where the problems
are, not precise rates; the judge is the same model that answers; I chose
the expected facts, and an answer can be right while missing my phrase; in
the learning table the first row is circular (the simulated user rates by
the same expected documents it counts).

</details>

<details>
<summary><b>Production: on-premise, with models on Azure OpenAI</b></summary>

- **Models:** `LLM_PROVIDER=azure` and `EMBEDDING_PROVIDER=azure` build
  PydanticAI's Azure model and an Azure embedding client from the
  deployment names. The configuration is unit-tested; **the Azure path has
  not been run against Azure** (no quota on the trial account).
- **Vector store:** the demo keeps the index in memory and rebuilds it at
  start (about 170 chunks, under a second). For production I would use
  pgvector: the class and department filters are one SQL `WHERE`;
  documents, metadata and vectors change in one transaction; and it is a
  database to run, not a new kind of system. It would also store the
  embedding model next to the vectors and refuse a query embedded by
  another model. It is one class behind the same `add` / `search`
  interface; it is not implemented here.
- **Monitoring:** `monitoring.py` keeps records in memory for the notebook;
  production would send the same records to OpenTelemetry, which
  PydanticAI already uses for model calls.

</details>

<details>
<summary><b>Assumptions and questions I would ask the business</b></summary>

| What was unclear | What I assumed | Alternative I considered |
|---|---|---|
| Which document wins when two disagree? | Kind first (policy, standard, guide, runbook), then support by other documents; never the newest alone (in 3 of our conflicts the weaker document is the newer one) | Newest wins; the model decides |
| Who settles a contradiction nobody can decide? | The answer names both owners and stops | Escalate to a fixed role |
| Who may see what? | Three classes (public, internal, confidential); the caller's clearance filters the search | Per-department access lists |
| May document text go to Azure OpenAI? | Yes for internal documents. The two confidential ones go to the model too when the caller has confidential clearance, which the bank's own rule in the corpus (CMP-2) allows only with pseudonymisation and a sign-off | Keep confidential text on-premise and answer it with a local model |
| What is a successful answer? | It cites at least one source and no agent failed | Rated useful by the asker |
| Should old rules be answerable? | Yes, when the question asks about the past | Delete superseded versions |
| Where does feedback come from? | Simulated: a user rating each source | Thumbs up or down on the whole answer |

</details>

<details>
<summary><b>Known gaps</b></summary>

- Retrieval on unfamiliar wording (above). Offline, the 0.4 bar does not
  stop the 7 out-of-scope questions.
- The offline stand-in writes templated answers and finds no conflicts; it
  exists so the notebook and the tests run without a key, and design
  choices were judged in model mode.
- Conflict detection varies between runs (Q08 and Q15 each missed once in
  four runs), and the faults listed under the evaluation numbers.
- Not run against Azure.

</details>
