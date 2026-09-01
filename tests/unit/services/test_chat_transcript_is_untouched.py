"""Condensing changes what the model sees. It must never change what was said.

Written before the condensation itself, deliberately: the property is easy to break and
invisible when broken — a transcript that quietly rewrote itself would look fine until
somebody scrolled back, and `add-privacy-controls` promised an export of what was actually
said.

`chat_service` writes the message rows before and after the agent runs, so the middlewares
that trim the model's view cannot reach them. These tests hold that arrangement in place
rather than trusting it to stay true.
"""

import json

import pytest
from sqlalchemy import func, select

from core.config import Settings
from data.models import Message
from data.repositories.messages import MessageRepository
from tests.secrets import TEST_JWT_SECRET


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret=TEST_JWT_SECRET, openrouter_api_key="sk-test", _env_file=None)


@pytest.fixture
def a_conversation(db, owner, now, sample_plant):
    """Several turns already on the record, with tool calls on the assistant replies."""
    messages = MessageRepository(db)
    for turn in range(6):
        messages.create(
            owner,
            plant_id=sample_plant,
            role="user",
            content=f"Question {turn}: why are the leaves like this?",
            tool_calls=None,
            now=now(),
        )
        messages.create(
            owner,
            plant_id=sample_plant,
            role="assistant",
            content=f"Answer {turn}: because of the watering.",
            tool_calls=[
                {
                    "name": "search_plant_knowledge",
                    "args": {"query": f"question {turn}"},
                    "result": "a passage about overwatering " * 20,
                }
            ],
            now=now(),
        )
    db.flush()
    return sample_plant


def _rows(db, plant_id) -> list[Message]:
    return list(
        db.scalars(
            select(Message).where(Message.plant_id == plant_id).order_by(Message.created_at)
        ).all()
    )


class TestTheRecordIsWhatWasSaid:
    def test_every_message_is_kept(self, db, owner, a_conversation):
        assert db.scalar(select(func.count()).select_from(Message)) == 12

    def test_nothing_is_truncated(self, db, owner, a_conversation):
        """A record that shortened itself to save tokens would be a different thing from a
        transcript."""
        for row in _rows(db, a_conversation):
            assert not row.content.endswith("…")
            assert "[cleared]" not in row.content

    def test_the_oldest_turn_is_still_readable_in_full(self, db, owner, a_conversation):
        first = _rows(db, a_conversation)[0]

        assert first.content == "Question 0: why are the leaves like this?"

    def test_what_an_old_reply_consulted_survives(self, db, owner, a_conversation):
        """The timeline reads escalations out of stored tool calls, and a reply's sources are
        shown beside it. Clearing tool output from the *model's* view must not reach these."""
        oldest_reply = _rows(db, a_conversation)[1]
        calls = json.loads(oldest_reply.tool_calls_json)

        assert calls[0]["name"] == "search_plant_knowledge"
        assert len(calls[0]["result"]) > 100

    def test_the_history_the_screen_reads_is_complete(self, db, owner, a_conversation):
        history = MessageRepository(db).list_for_plant(owner, a_conversation)

        assert len(history) == 12
        assert history[0].content.startswith("Question 0")
        assert history[-1].content.startswith("Answer 5")


class TestAnExportCarriesAllOfIt:
    def test_every_message_reaches_the_archive(self, db, owner, a_conversation, settings):
        """`add-privacy-controls` promised somebody a copy of what was said. Condensing what
        the model sees must not quietly narrow that promise."""
        import io
        import zipfile

        from core.blobs import PostgresBlobStore
        from services import export
        from tests.accounts import NOW

        built = export.build(
            db,
            user_id=owner,
            blobs=PostgresBlobStore(db),
            settings=settings,
            now=NOW,
        )
        manifest = json.loads(zipfile.ZipFile(io.BytesIO(built.content)).read(export.MANIFEST))

        conversation = manifest["plants"][0]["conversation"]
        assert len(conversation) == 12
        assert conversation[0]["said"].startswith("Question 0")
        assert conversation[-1]["said"].startswith("Answer 5")

    def test_and_what_each_reply_consulted(self, db, owner, a_conversation, settings):
        import io
        import zipfile

        from core.blobs import PostgresBlobStore
        from services import export
        from tests.accounts import NOW

        built = export.build(
            db, user_id=owner, blobs=PostgresBlobStore(db), settings=settings, now=NOW
        )
        manifest = json.loads(zipfile.ZipFile(io.BytesIO(built.content)).read(export.MANIFEST))

        consulted = [
            m["consulted"] for m in manifest["plants"][0]["conversation"] if m["consulted"]
        ]
        assert len(consulted) == 6
        assert consulted[0][0]["name"] == "search_plant_knowledge"
