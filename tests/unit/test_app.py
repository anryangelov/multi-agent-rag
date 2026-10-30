"""The assistant built from settings, and the command line on top of it."""

import pytest

from rag_system.__main__ import main
from rag_system.app import Assistant, as_markdown
from rag_system.config import Settings

DEPLOY = (
    "What's the process for deploying a new microservice and what "
    "compliance checks are needed?"
)


@pytest.fixture(scope="module")
def offline() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture(scope="module")
def assistant(offline) -> Assistant:
    return Assistant(offline)


async def test_the_assistant_answers_from_the_whole_corpus(assistant):
    answer = await assistant.ask(DEPLOY)

    cited = {source.doc_id for source in answer.sources}
    assert {"TEC-1", "CMP-4"} <= cited


def test_the_assistant_says_when_it_runs_on_the_offline_stand_in(assistant):
    assert "OFFLINE stand-in" in assistant.describe()
    assert "minishlab/potion-base-8M" in assistant.describe()


def test_a_new_store_is_a_separate_index_of_the_same_documents(assistant):
    copy = assistant.new_store()

    assert copy is not assistant.store
    assert copy.model == assistant.store.model
    assert len(assistant.documents) == 26


async def test_the_markdown_answer_lists_every_source_with_version_and_date(
    assistant,
):
    answer = await assistant.ask(DEPLOY)

    text = as_markdown(answer)

    assert text.startswith(answer.text)
    assert "**Sources**" in text
    tec_1 = next(s for s in answer.sources if s.doc_id == "TEC-1")
    assert f"- [TEC-1] {tec_1.title}, v{tec_1.version}, {tec_1.effective_date}" in text


def test_the_command_line_prints_the_answer_and_its_sources(offline, capsys):
    main([DEPLOY], settings=offline)

    out, err = capsys.readouterr()
    assert "[TEC-1]" in out
    assert "**Sources**" in out
    assert "OFFLINE stand-in" in err


def test_the_command_line_refuses_an_empty_question(offline, capsys):
    with pytest.raises(SystemExit) as exit:
        main(["   "], settings=offline)

    assert exit.value.code == 2
    assert "the question is empty" in capsys.readouterr().err
