"""The synthetic corpus and the eval questions stay consistent.

The conflict resolution and the classification filter depend on the
metadata in `data/`; a wrong date or a broken reference would change what
the system answers. These tests read the files directly.
"""

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from rag_system.messages import Classification, Domain, Kind
from tests.evals.gold_set import ALL_QUESTIONS as QUESTIONS
from tests.evals.measures import mentions

ROOT = Path(__file__).parents[2]
REQUIRED = {
    "id",
    "title",
    "domain",
    "kind",
    "version",
    "effective_date",
    "classification",
    "owner",
}


def _load() -> dict[str, tuple[dict, str, Path]]:
    docs = {}
    for path in sorted((ROOT / "data").rglob("*.md")):
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", path.read_text(), re.S)
        assert match, f"{path} has no front matter"
        meta = yaml.safe_load(match.group(1))
        docs[meta["id"]] = (meta, match.group(2), path)
    return docs


DOCS = _load()
# A document is superseded when a newer one names it in `supersedes`.
SUPERSEDED = {
    meta["supersedes"] for meta, _, _ in DOCS.values() if "supersedes" in meta
}


def test_documents_per_domain():
    counts = Counter(meta["domain"] for meta, _, _ in DOCS.values())
    assert counts == {"technical": 9, "business": 9, "compliance": 8}


@pytest.mark.parametrize("doc_id", sorted(DOCS))
def test_front_matter_is_complete_and_valid(doc_id):
    meta, _, path = DOCS[doc_id]
    assert REQUIRED <= meta.keys()
    assert meta["kind"] in set(Kind)
    assert meta["classification"] in set(Classification)
    assert doc_id.startswith(Domain(meta["domain"]).prefix + "-")
    assert path.parent.name == meta["domain"]
    assert path.name.startswith(doc_id + "-")


@pytest.mark.parametrize("doc_id", sorted(DOCS))
def test_length_depends_on_structure(doc_id):
    """Structured documents are short; unstructured ones are long on purpose."""
    _, body, _ = DOCS[doc_id]
    words = len(body.split())
    if re.search(r"(?m)^## ", body):
        assert 300 <= words <= 600
    else:
        assert 1000 <= words <= 2000


def test_exactly_two_unstructured_documents():
    unstructured = {
        i for i, (_, body, _) in DOCS.items() if not re.search(r"(?m)^## ", body)
    }
    assert unstructured == {"BUS-9", "TEC-9"}


@pytest.mark.parametrize("doc_id", sorted(DOCS))
def test_references_point_to_existing_documents(doc_id):
    _, body, _ = DOCS[doc_id]
    refs = set(re.findall(r"\b(?:TEC|BUS|CMP)-\d+\b", body))
    assert refs <= DOCS.keys()


def test_a_new_version_supersedes_an_older_one_of_the_same_document():
    newer = [meta for meta, _, _ in DOCS.values() if "supersedes" in meta]
    assert {meta["supersedes"] for meta in newer} == {"TEC-2", "BUS-1"}
    for meta in newer:
        old = DOCS[meta["supersedes"]][0]
        assert old["title"] == meta["title"]
        assert old["version"] < meta["version"]
        assert old["effective_date"] < meta["effective_date"]


def test_exactly_two_confidential_documents():
    confidential = {
        i for i, (m, _, _) in DOCS.items() if m["classification"] == "confidential"
    }
    assert confidential == {"BUS-8", "CMP-8"}


@pytest.mark.parametrize("question", QUESTIONS, ids=lambda q: q["id"])
def test_eval_question_expects_existing_documents_of_its_domains(question):
    expected = question["expected_documents"]
    assert set(expected) <= DOCS.keys()
    domains = {DOCS[doc_id][0]["domain"] for doc_id in expected}
    assert domains == set(question["expected_domains"])
    assert question.get("clearance", "internal") in set(Classification)


@pytest.mark.parametrize("question", QUESTIONS, ids=lambda q: q["id"])
def test_eval_question_clearance_allows_its_expected_documents(question):
    clearance = Classification(question.get("clearance", "internal"))
    for doc_id in question["expected_documents"]:
        assert clearance.allows(Classification(DOCS[doc_id][0]["classification"]))


@pytest.mark.parametrize("question", QUESTIONS, ids=lambda q: q["id"])
def test_a_superseded_document_is_expected_only_in_a_question_about_history(question):
    history = question.get("include_superseded", False)
    for doc_id in question["expected_documents"]:
        if doc_id in SUPERSEDED:
            assert history, f"{doc_id} is superseded; mark the question as history"
    for doc_id in question.get("forbidden_documents", []):
        assert doc_id in DOCS


@pytest.mark.parametrize("question", QUESTIONS, ids=lambda q: q["id"])
def test_every_expected_fact_is_stated_in_an_expected_document(question):
    texts = [DOCS[doc_id][1] for doc_id in question["expected_documents"]]
    for fact in question["expected_facts"]:
        assert any(mentions(text, fact) for text in texts), fact
