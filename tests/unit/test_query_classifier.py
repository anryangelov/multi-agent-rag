"""The classifier decides which domains a question needs and what each is asked."""

from datetime import date

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from rag_system.ingestion import Document, chunk_document
from rag_system.messages import Classification, Domain, Kind, Plan, SubQuery
from rag_system.offline_model import offline_model
from rag_system.query_classifier import QueryClassifier
from rag_system.vector_store import InMemoryVectorStore
from tests.fakes import WordHashEmbedder


def document(
    doc_id: str,
    body: str,
    domain: Domain,
    classification: Classification = Classification.INTERNAL,
) -> Document:
    return Document(
        id=doc_id,
        title=f"Document {doc_id}",
        domain=domain,
        kind=Kind.GUIDE,
        version=1,
        effective_date=date(2026, 1, 1),
        status="current",
        classification=classification,
        owner="Platform Engineering",
        body=body,
    )


def store_with(*documents: Document) -> InMemoryVectorStore:
    store = InMemoryVectorStore(WordHashEmbedder())
    for each in documents:
        store.add(chunk_document(each))
    return store


# 8 chunks about deployments (technical and compliance), 4 about other things
# (business): the 8 nearest chunks to a deployment question are the first 8.
DEPLOYMENT_CORPUS = [
    *[
        document(
            f"TEC-{n}", f"Deploy a microservice: deployment step {n}.", Domain.TECHNICAL
        )
        for n in range(1, 6)
    ],
    *[
        document(
            f"CMP-{n}",
            f"Deploy a microservice: compliance check {n}.",
            Domain.COMPLIANCE,
        )
        for n in range(1, 4)
    ],
    *[
        document(f"BUS-{n}", text, Domain.BUSINESS)
        for n, text in [
            (1, "Quarterly invoices list every vendor contract."),
            (2, "Office plants are watered on Fridays."),
            (3, "The canteen menu changes every week."),
            (4, "Parking badges expire after twelve months."),
        ]
    ],
]


async def test_offline_the_plan_asks_every_domain_among_the_8_nearest_chunks():
    classifier = QueryClassifier(store_with(*DEPLOYMENT_CORPUS), offline_model())
    question = "How do I deploy a microservice?"

    plan = await classifier.classify(question, Classification.INTERNAL)

    asked = [sub_query.domain for sub_query in plan.sub_queries]
    assert asked == [Domain.TECHNICAL, Domain.COMPLIANCE]
    assert all(sub_query.text == question for sub_query in plan.sub_queries)


async def test_a_domain_found_only_in_documents_above_the_clearance_is_not_asked():
    store = store_with(
        *[
            document(f"TEC-{n}", f"Deploy a microservice: step {n}.", Domain.TECHNICAL)
            for n in range(1, 4)
        ],
        document(
            "CMP-8",
            "Deploy a microservice: the incident report.",
            Domain.COMPLIANCE,
            Classification.CONFIDENTIAL,
        ),
    )
    classifier = QueryClassifier(store, offline_model())

    plan = await classifier.classify(
        "How do I deploy a microservice?", Classification.INTERNAL
    )

    assert [sub_query.domain for sub_query in plan.sub_queries] == [Domain.TECHNICAL]


async def test_with_a_model_the_model_sees_the_chunks_and_writes_the_plan():
    prompts = []

    def model_that_routes_to_compliance(messages, info):
        """Stands in for a real model: rewrites the question for one domain."""
        prompts.append(messages[-1].parts[-1].content)
        plan = {"sub_queries": [{"domain": "compliance", "text": "Checks?"}]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, plan)])

    classifier = QueryClassifier(
        store_with(*DEPLOYMENT_CORPUS), FunctionModel(model_that_routes_to_compliance)
    )

    plan = await classifier.classify(
        "How do I deploy a microservice?", Classification.INTERNAL
    )

    assert plan == Plan(sub_queries=[SubQuery(domain="compliance", text="Checks?")])
    assert prompts[0].count("<chunk ") == 8
    assert 'domain="technical"' in prompts[0]
    assert 'domain="compliance"' in prompts[0]
