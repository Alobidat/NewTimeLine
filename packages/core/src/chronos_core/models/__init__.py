"""ORM models. Importing this package registers every table on ``Base.metadata``
(needed by Alembic autogenerate + create_all)."""

from chronos_core.models.agent_run import AgentRun
from chronos_core.models.bot import BotProfile
from chronos_core.models.component_health import ComponentHealth
from chronos_core.models.config import Config, ConfigAudit
from chronos_core.models.entity import Entity, EventEntity
from chronos_core.models.enums import EventStatus, IngestState, TimePrecision
from chronos_core.models.event import EMBEDDING_DIM, Event, EventReference
from chronos_core.models.friendship import Friendship
from chronos_core.models.ingest import IngestItem
from chronos_core.models.log_record import LogRecord
from chronos_core.models.metric_sample import MetricSample
from chronos_core.models.interaction import (
    Comment,
    CommentReaction,
    Reaction,
    SourceVote,
)
from chronos_core.models.media import EventMedia, Media, MediaSource
from chronos_core.models.moderation import ModerationFlag
from chronos_core.models.relation import EventRelation
from chronos_core.models.social import (
    ActivityLog,
    Bookmark,
    Follow,
    Notification,
    Promote,
    Repost,
)
from chronos_core.models.source import EventSource, Source
from chronos_core.models.user import User, UserAgreement, UserIdentity

__all__ = [
    "AgentRun",
    "BotProfile",
    "ComponentHealth",
    "Config",
    "ConfigAudit",
    "LogRecord",
    "MetricSample",
    "Entity",
    "EventEntity",
    "EventStatus",
    "IngestState",
    "TimePrecision",
    "EMBEDDING_DIM",
    "Event",
    "EventReference",
    "Friendship",
    "EventMedia",
    "Media",
    "MediaSource",
    "ModerationFlag",
    "EventRelation",
    "ActivityLog",
    "Bookmark",
    "Follow",
    "Notification",
    "Promote",
    "Repost",
    "IngestItem",
    "Comment",
    "CommentReaction",
    "Reaction",
    "SourceVote",
    "EventSource",
    "Source",
    "User",
    "UserIdentity",
    "UserAgreement",
]
