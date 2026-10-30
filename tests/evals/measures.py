"""The offline measures that the tuning evals and the held-out evals share.

questions --> classifier_counts  the domains of each plan
          --> store_counts       the documents of the top 5 per domain
          --> agent_counts       the documents the domain agents cite
"""

from pathlib import Path

from rag_system.domain_agents import DomainAgent
from rag_system.ingestion import chunk_document, load_documents
from rag_system.messages import AgentTask, Classification, Domain, SubQuery
from rag_system.offline_model import offline_model
from rag_system.orchestrator import Orchestrator
from rag_system.query_classifier import QueryClassifier
from rag_system.vector_store import InMemoryVectorStore

LIMIT = 5
CHUNK_TEXTS = {
    chunk.id: chunk.text
    for document in load_documents(Path(__file__).parents[2] / "data")
    for chunk in chunk_document(document)
}
EVERY_CHUNK = 1000  # more than the corpus holds (about 170 chunks)


def clearance_of(question: dict) -> Classification:
    return Classification(question.get("clearance", "internal"))


async def classifier_counts(store: InMemoryVectorStore, questions: list[dict]):
    """(expected domains found, extra domains, exact plans, missed domains)."""
    classifier = QueryClassifier(store, offline_model())
    found, extra, exact, missed = 0, 0, 0, []
    for question in questions:
        plan = await classifier.classify(question["question"], clearance_of(question))
        asked = {sub_query.domain for sub_query in plan.sub_queries}
        expected = {Domain(domain) for domain in question["expected_domains"]}
        found += len(asked & expected)
        extra += len(asked - expected)
        exact += asked == expected
        missed += [f"{question['id']}: {domain}" for domain in expected - asked]
    return found, extra, exact, missed


def found_documents(store: InMemoryVectorStore, question: dict) -> set[str]:
    """The documents of the hits in every expected domain of the question."""
    found = set()
    for domain in question["expected_domains"]:
        hits = store.search(
            question["question"],
            Domain(domain),
            clearance_of(question),
            limit=LIMIT,
            include_superseded=question.get("include_superseded", False),
        )
        found |= {hit.chunk.document.id for hit in hits}
    return found


def store_counts(store: InMemoryVectorStore, questions: list[dict]):
    """(expected documents in the top 5, expected documents, missed)."""
    found, expected, missed = 0, 0, []
    for question in questions:
        documents = found_documents(store, question)
        for doc_id in question["expected_documents"]:
            expected += 1
            if doc_id in documents:
                found += 1
            else:
                missed.append(f"{question['id']}: {doc_id}")
    return found, expected, missed


async def agent_counts(store: InMemoryVectorStore, questions: list[dict]):
    """(expected documents the agents cite, missed): each expected domain's
    agent with the offline model, i.e. dynamic retrieval end to end."""
    agents = {domain: DomainAgent(domain, store, offline_model()) for domain in Domain}
    found, missed = 0, []
    for question in questions:
        cited = set()
        for domain in question["expected_domains"]:
            task = AgentTask(
                question=question["question"],
                sub_query=SubQuery(domain=domain, text=question["question"]),
                clearance=clearance_of(question),
            )
            answer = await agents[Domain(domain)].answer(task)
            for claim in answer.claims:
                cited |= {citation.doc_id for citation in claim.citations}
        for doc_id in question["expected_documents"]:
            if doc_id in cited:
                found += 1
            else:
                missed.append(f"{question['id']}: {doc_id}")
    return found, missed


def document_ranks(store: InMemoryVectorStore, questions: list[dict]) -> list[int]:
    """The rank of each expected document among the documents of its domain.

    The store orders every chunk of the domain (hybrid search); a document
    takes the place of its best chunk. Rank 1 is the first document.
    """
    ranks = []
    for question in questions:
        for doc_id in question["expected_documents"]:
            prefix = doc_id.split("-")[0]
            domain = next(domain for domain in Domain if domain.prefix == prefix)
            hits = store.search(
                question["question"],
                domain,
                clearance_of(question),
                limit=EVERY_CHUNK,
                include_superseded=question.get("include_superseded", False),
            )
            order = list(dict.fromkeys(hit.chunk.document.id for hit in hits))
            ranks.append(order.index(doc_id) + 1)
    return ranks


def mentions(text: str, fact: str) -> bool:
    """Whether `text` states `fact` word for word, ignoring case, Markdown
    bold and line breaks: "**two approvers**" mentions "two approvers"."""

    def plain(words: str) -> str:
        return " ".join(words.replace("*", "").lower().split())

    return plain(fact) in plain(text)


async def fact_counts(store: InMemoryVectorStore, questions: list[dict]):
    """(expected facts in the chunks the agents kept, expected facts, missed).

    The whole pipeline runs with the offline model, which turns every kept
    chunk into a claim, so the chunks cited are the chunks kept.
    """
    orchestrator = Orchestrator(store, offline_model())
    found, expected, missed = 0, 0, []
    for question in questions:
        answer = await orchestrator.answer(question["question"], clearance_of(question))
        kept = [
            CHUNK_TEXTS[citation.chunk_id]
            for agent_answer in answer.agent_answers
            for claim in agent_answer.claims
            for citation in claim.citations
        ]
        for fact in question["expected_facts"]:
            expected += 1
            if any(mentions(text, fact) for text in kept):
                found += 1
            else:
                missed.append(f"{question['id']}: {fact}")
    return found, expected, missed
