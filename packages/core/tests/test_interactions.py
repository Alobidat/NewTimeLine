"""Unit tests for the interaction substrate (ADR-0025): DTO validation + the branching
logic in chronos_core.interactions_repo (parent checks, author guards, toggle, vote upsert,
self-loop + ownership on links).

Pure-logic: a tiny in-memory fake session stands in for AsyncSession so we exercise the
helpers without a database (the project has no DB test fixture). Aggregate-read helpers that
emit raw SQL are covered by the integration suite, not here.
"""

from __future__ import annotations

import uuid

import pytest
from chronos_core import interactions_repo as repo
from chronos_core.models.interaction import (
    REACTION_KINDS,
    VOTE_VERDICTS,
    Comment,
    Reaction,
    SourceVote,
)
from chronos_core.models.relation import EventRelation
from chronos_core.schemas.interaction import (
    CommentCreate,
    EventLinkCreate,
    ReactionToggle,
    SourceVoteCast,
)
from pydantic import ValidationError


# --- a minimal in-memory async "session" ---------------------------------------------


class FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class FakeSession:
    """Supports the subset interactions_repo uses for its branching paths: get/add/delete/
    flush + a delete(stmt) that matches EventRelation rows by (src, dst, kind, created_by)."""

    def __init__(self) -> None:
        self.objects: list[object] = []

    def _pk(self, obj):
        if isinstance(obj, Comment):
            return ("Comment", obj.id)
        if isinstance(obj, Reaction):
            return ("Reaction", obj.user_id, obj.event_id, obj.kind)
        if isinstance(obj, SourceVote):
            return ("SourceVote", obj.user_id, obj.event_id, obj.source_id)
        if isinstance(obj, EventRelation):
            return ("EventRelation", obj.src_event, obj.dst_event, obj.kind)
        return None

    async def get(self, model, key):
        name = model.__name__
        if name == "Comment":
            target = ("Comment", key)
        elif name == "Reaction":
            target = ("Reaction", *key)
        elif name == "SourceVote":
            target = ("SourceVote", *key)
        elif name == "EventRelation":
            target = ("EventRelation", *key)
        else:  # pragma: no cover
            target = None
        for obj in self.objects:
            if self._pk(obj) == target:
                return obj
        return None

    def add(self, obj) -> None:
        if getattr(obj, "id", None) is None and isinstance(obj, Comment):
            obj.id = uuid.uuid4()
        self.objects.append(obj)

    async def delete(self, obj) -> None:
        self.objects.remove(obj)

    async def flush(self) -> None:
        for obj in self.objects:
            if isinstance(obj, Comment) and obj.id is None:
                obj.id = uuid.uuid4()

    async def execute(self, stmt):
        # Only used here for delete(EventRelation) in remove_user_link. Match in-memory rows
        # whose (src, dst, kind, created_by) all appear among the WHERE's bound values —
        # tolerant of SQLAlchemy's internal param naming.
        values = set(str(v) for v in stmt.compile().params.values())
        before = len(self.objects)
        self.objects = [
            o
            for o in self.objects
            if not (
                isinstance(o, EventRelation)
                and str(o.src_event) in values
                and str(o.dst_event) in values
                and str(o.kind) in values
                and str(o.created_by) in values
            )
        ]
        return FakeResult(before - len(self.objects))


# --- DTO validation -------------------------------------------------------------------


def test_comment_create_rejects_empty_body():
    with pytest.raises(ValidationError):
        CommentCreate(body="")
    assert CommentCreate(body="hi").parent_id is None


def test_reaction_toggle_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        ReactionToggle(kind="love")
    for k in REACTION_KINDS:
        assert ReactionToggle(kind=k).kind == k


def test_source_vote_cast_rejects_unknown_verdict():
    with pytest.raises(ValidationError):
        SourceVoteCast(source_id=uuid.uuid4(), verdict="nope")
    for v in VOTE_VERDICTS:
        assert SourceVoteCast(source_id=uuid.uuid4(), verdict=v).verdict == v


def test_event_link_create_defaults_to_thematic():
    link = EventLinkCreate(src_event=uuid.uuid4(), dst_event=uuid.uuid4())
    assert link.kind == "thematic"


# --- comments -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_comment_and_reply_validates_parent():
    s = FakeSession()
    ev = uuid.uuid4()
    actor = uuid.uuid4()
    top = await repo.create_comment(s, event_id=ev, user_id=actor, body="top")
    assert top.status == "visible"
    reply = await repo.create_comment(
        s, event_id=ev, user_id=actor, body="reply", parent_id=top.id
    )
    assert reply.parent_id == top.id

    # Parent on a different event is rejected.
    with pytest.raises(ValueError):
        await repo.create_comment(
            s, event_id=uuid.uuid4(), user_id=actor, body="x", parent_id=top.id
        )


@pytest.mark.asyncio
async def test_edit_and_delete_require_authorship():
    s = FakeSession()
    ev = uuid.uuid4()
    owner = uuid.uuid4()
    other = uuid.uuid4()
    c = await repo.create_comment(s, event_id=ev, user_id=owner, body="mine")

    with pytest.raises(PermissionError):
        await repo.edit_comment(s, c.id, user_id=other, body="hacked")
    edited = await repo.edit_comment(s, c.id, user_id=owner, body="edited")
    assert edited.body == "edited"

    with pytest.raises(PermissionError):
        await repo.soft_delete_comment(s, c.id, user_id=other)
    removed = await repo.soft_delete_comment(s, c.id, user_id=owner)
    assert removed.status == "removed"

    # Missing comment → None (not an error).
    assert await repo.edit_comment(s, uuid.uuid4(), user_id=owner, body="x") is None


# --- reactions ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_reaction_adds_then_removes():
    s = FakeSession()
    ev, actor = uuid.uuid4(), uuid.uuid4()
    assert await repo.toggle_reaction(s, event_id=ev, user_id=actor, kind="like") is True
    assert any(isinstance(o, Reaction) for o in s.objects)
    # Toggling the same kind again removes it.
    assert await repo.toggle_reaction(s, event_id=ev, user_id=actor, kind="like") is False
    assert not any(isinstance(o, Reaction) for o in s.objects)


@pytest.mark.asyncio
async def test_toggle_reaction_rejects_bad_kind():
    s = FakeSession()
    with pytest.raises(ValueError):
        await repo.toggle_reaction(s, event_id=uuid.uuid4(), user_id=uuid.uuid4(), kind="love")


# --- source votes ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cast_source_vote_upserts():
    s = FakeSession()
    ev, src, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    v1 = await repo.cast_source_vote(
        s, event_id=ev, source_id=src, user_id=actor, verdict="corroborate"
    )
    assert v1.verdict == "corroborate"
    # Re-casting changes the existing row in place (no duplicate).
    v2 = await repo.cast_source_vote(
        s, event_id=ev, source_id=src, user_id=actor, verdict="dispute"
    )
    assert v2 is v1 and v2.verdict == "dispute"
    assert sum(isinstance(o, SourceVote) for o in s.objects) == 1


@pytest.mark.asyncio
async def test_cast_source_vote_rejects_bad_verdict():
    s = FakeSession()
    with pytest.raises(ValueError):
        await repo.cast_source_vote(
            s, event_id=uuid.uuid4(), source_id=uuid.uuid4(), user_id=uuid.uuid4(), verdict="x"
        )


# --- user event links -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_user_link_records_actor_and_dedups():
    s = FakeSession()
    a, b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert await repo.add_user_link(s, src_event=a, dst_event=b, kind="thematic", user_id=actor) is True
    edge = next(o for o in s.objects if isinstance(o, EventRelation))
    # created_by is the actor's id as a string → /related can tag it origin="user".
    assert edge.created_by == str(actor)
    # Idempotent per kind.
    assert await repo.add_user_link(s, src_event=a, dst_event=b, kind="thematic", user_id=actor) is False


@pytest.mark.asyncio
async def test_add_user_link_rejects_self_loop():
    s = FakeSession()
    a, actor = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ValueError):
        await repo.add_user_link(s, src_event=a, dst_event=a, kind="thematic", user_id=actor)


@pytest.mark.asyncio
async def test_remove_user_link_only_removes_own_edge():
    s = FakeSession()
    a, b, actor, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await repo.add_user_link(s, src_event=a, dst_event=b, kind="thematic", user_id=actor)
    # Another user's edge is not removed.
    assert await repo.remove_user_link(
        s, src_event=a, dst_event=b, kind="thematic", user_id=other
    ) is False
    # The owner's edge is.
    assert await repo.remove_user_link(
        s, src_event=a, dst_event=b, kind="thematic", user_id=actor
    ) is True
    assert not any(isinstance(o, EventRelation) for o in s.objects)
