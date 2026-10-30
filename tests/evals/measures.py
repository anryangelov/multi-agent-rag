"""The offline measures that the tuning evals and the held-out evals share.

questions --> classifier_counts  the domains of each plan
          --> store_counts       the documents of the top 5 per domain
          --> agent_counts       the documents the domain agents cite
"""

from rag_system.domain_agents import DomainAgent
from rag_system.messages import AgentTask, Classification, Domain, SubQuery
from rag_system.offline_model import offline_model
from rag_system.query_classifier import QueryClassifier
from rag_system.vector_store import InMemoryVectorStore

LIMIT = 5


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
