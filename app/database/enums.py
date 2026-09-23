# Enum types used by the database models.
#
# Inheriting from both str and enum.Enum keeps enum values JSON-friendly
# while still giving us ORM validation and database CHECK constraints.

import enum


class JobStatus(str, enum.Enum):
    DRAFT = "Draft"
    ACTIVE = "Active"
    PAUSED = "Paused"
    CLOSED = "Closed"


class Platform(str, enum.Enum):
    FACEBOOK = "Facebook"
    TELEGRAM = "Telegram"
    TIKTOK = "TikTok"


class PostingMethod(str, enum.Enum):
    API = "API"
    BROWSER_ASSISTED = "Browser-assisted"
    MANUAL = "Manual"


class PostStatus(str, enum.Enum):
    DRAFT = "Draft"
    QUEUED = "Queued"
    SCHEDULED = "Scheduled"
    PROCESSING = "Processing"
    POSTED = "Posted"
    FAILED = "Failed"
    SKIPPED = "Skipped"
    MANUAL_ACTION_REQUIRED = "Manual Action Required"
