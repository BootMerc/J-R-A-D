"""Destination business logic: create/update field mapping (tags handled
separately from scalar fields), activate/deactivate, and CSV import/export.

CSV import processes rows independently — one bad row (invalid platform,
missing name) doesn't abort the other 99. Matches Section 24's "never
silently fail" by returning exactly which rows failed and why, rather than
an all-or-nothing transaction.
"""

from __future__ import annotations
# ^ This class defines a method named `list` — see destination_repository.py
# for why every class with a `list()` method needs this.

import csv
import io
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.database.enums import Platform, PostingMethod
from app.database.models import Destination
from app.database.repositories.destination_repository import DestinationRepository
from app.schemas.destination import DestinationCreate, DestinationUpdate
from app.services.exceptions import NotFoundError

# Sensible default posting_method per platform when a CSV row doesn't
# specify one. Matches the Phase 1 architecture assessment: Telegram's Bot
# API supports real posting automation, Facebook Groups don't have a
# third-party posting API at all, TikTok's API needs an audit most
# individual developer apps won't have.
_DEFAULT_POSTING_METHOD = {
    Platform.TELEGRAM: PostingMethod.API,
    Platform.FACEBOOK: PostingMethod.BROWSER_ASSISTED,
    Platform.TIKTOK: PostingMethod.MANUAL,
}

_CSV_COLUMNS = [
    "platform", "name", "url", "category", "location", "audience",
    "language", "posting_method", "active", "notes", "tags",
]


@dataclass
class ImportResult:
    created: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_enum(raw: str, enum_cls, field_name: str):
    normalized = raw.strip().lower()
    mapping = {member.value.lower(): member for member in enum_cls}
    if normalized not in mapping:
        valid = ", ".join(member.value for member in enum_cls)
        raise ValueError(f"invalid {field_name} '{raw}' (expected one of: {valid})")
    return mapping[normalized]


class DestinationService:
    def __init__(self, db: Session):
        self.repo = DestinationRepository(db)

    def create(self, payload: DestinationCreate) -> Destination:
        data = payload.model_dump(exclude={"tags"})
        return self.repo.create(tag_names=payload.tags, **data)

    def get(self, destination_id: int) -> Optional[Destination]:
        return self.repo.get(destination_id)

    def list(
        self,
        platform: Optional[Platform] = None,
        category: Optional[str] = None,
        location: Optional[str] = None,
        language: Optional[str] = None,
        tag: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Destination], int]:
        items = self.repo.list(
            platform=platform, category=category, location=location, language=language,
            tag=tag, active=active, search=search, skip=skip, limit=limit,
        )
        total = self.repo.count(
            platform=platform, category=category, location=location, language=language,
            tag=tag, active=active, search=search,
        )
        return items, total

    def filter_options(self) -> dict:
        return {
            "categories": self.repo.distinct_categories(),
            "locations": self.repo.distinct_locations(),
            "languages": self.repo.distinct_languages(),
        }

    def update(self, destination_id: int, payload: DestinationUpdate) -> Destination:
        data = payload.model_dump(exclude_unset=True, exclude={"tags"})
        # model_fields_set (not exclude_unset on tags) distinguishes "tags
        # not mentioned" (leave alone) from "tags explicitly sent" (replace,
        # even with an empty list to clear them).
        tag_names = payload.tags if "tags" in payload.model_fields_set else None

        destination = self.repo.update(destination_id, tag_names=tag_names, **data)
        if destination is None:
            raise NotFoundError(f"Destination {destination_id} not found")
        return destination

    def delete(self, destination_id: int) -> None:
        if not self.repo.delete(destination_id):
            raise NotFoundError(f"Destination {destination_id} not found")

    def set_active(self, destination_id: int, active: bool) -> Destination:
        destination = self.repo.update(destination_id, active=active)
        if destination is None:
            raise NotFoundError(f"Destination {destination_id} not found")
        return destination

    def import_csv(self, file_content: str) -> ImportResult:
        reader = csv.DictReader(io.StringIO(file_content))
        result = ImportResult()

        if reader.fieldnames is None:
            result.errors.append("CSV appears to be empty.")
            return result

        headers = {(h or "").strip().lower() for h in reader.fieldnames}
        if not {"platform", "name"}.issubset(headers):
            result.errors.append("CSV must have at least 'platform' and 'name' columns.")
            return result

        for row_number, raw_row in enumerate(reader, start=2):  # row 1 is the header
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
            try:
                if not row.get("platform"):
                    raise ValueError("platform is required")
                if not row.get("name"):
                    raise ValueError("name is required")

                platform = _parse_enum(row["platform"], Platform, "platform")
                posting_method = (
                    _parse_enum(row["posting_method"], PostingMethod, "posting_method")
                    if row.get("posting_method")
                    else _DEFAULT_POSTING_METHOD[platform]
                )
                active = row.get("active", "").lower() not in ("false", "0", "no") if row.get("active") else True
                tag_names = [t.strip() for t in row.get("tags", "").split("|") if t.strip()] or None

                self.repo.create(
                    platform=platform,
                    name=row["name"],
                    url=row.get("url") or None,
                    category=row.get("category") or None,
                    location=row.get("location") or None,
                    audience=row.get("audience") or None,
                    language=row.get("language") or None,
                    posting_method=posting_method,
                    active=active,
                    notes=row.get("notes") or None,
                    tag_names=tag_names,
                )
                result.created += 1
            except ValueError as exc:
                result.errors.append(f"Row {row_number}: {exc}")

        return result

    def export_csv(self) -> str:
        destinations = self.repo.list(limit=None)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(_CSV_COLUMNS)
        for d in destinations:
            writer.writerow([
                d.platform.value,
                d.name,
                d.url or "",
                d.category or "",
                d.location or "",
                d.audience or "",
                d.language or "",
                d.posting_method.value,
                "true" if d.active else "false",
                d.notes or "",
                "|".join(t.name for t in d.tags),
            ])
        return output.getvalue()
