# Post Creator + Queue business logic.
#
# generate_posts() and generate_variations() handle the Phase 5 workflows.
# create_queue() handles Phase 6 batch queue creation, using the same
# rendering approach but creating Queued posts with staggered scheduled_at times.
#
# All three workflows use _resolve_template_for_destination() so the
# platform matching and auto-select logic stays in one place.
#
# Rendering itself is handled by app/utils/template_rendering.py.
# This file doesn't add any new rendering logic.
#
# Each batch target is processed independently, so one bad
# destination/template won't stop the rest from being processed.

from __future__ import annotations
# ^ This class has a `list()` method — see destination_repository.py.

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.enums import Platform, PostStatus
from app.database.models import Destination, Post, PostTemplate
from app.database.repositories.destination_repository import DestinationRepository
from app.database.repositories.job_repository import JobRepository
from app.database.repositories.post_repository import PostRepository
from app.database.repositories.template_repository import TemplateRepository
from app.integrations.facebook.assistant import copy_content, open_destination
from app.integrations.telegram.bot import send_message
from app.integrations.tiktok.visual_generator import generate_recruitment_visual
from app.schemas.post import PostUpdate
from app.services.exceptions import NotFoundError
from app.utils.template_rendering import job_to_variables, render_template
from app.utils.time_utils import utcnow


class PostService:
    def __init__(self, db: Session):
        self.repo = PostRepository(db)
        self.job_repo = JobRepository(db)
        self.destination_repo = DestinationRepository(db)
        self.template_repo = TemplateRepository(db)

    def get(self, post_id: int) -> Optional[Post]:
        return self.repo.get(post_id)

    def list(
        self,
        job_id: Optional[int] = None,
        destination_id: Optional[int] = None,
        status: Optional[PostStatus] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Post], int]:
        items = self.repo.list(job_id=job_id, destination_id=destination_id, status=status, skip=skip, limit=limit)
        total = self.repo.count(job_id=job_id, destination_id=destination_id, status=status)
        return items, total

    def update(self, post_id: int, payload: PostUpdate) -> Post:
        data = payload.model_dump(exclude_unset=True)
        post = self.repo.update(post_id, **data)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")
        return post

    def delete(self, post_id: int) -> None:
        if not self.repo.delete(post_id):
            raise NotFoundError(f"Post {post_id} not found")

    def _auto_select_template(self, destination: Destination) -> Optional[PostTemplate]:
        """Prefers an active template matching both platform and language;
        falls back to any active template for the platform."""
        if destination.language:
            matches = self.template_repo.list(
                platform=destination.platform, language=destination.language, active=True, limit=1
            )
            if matches:
                return matches[0]
        matches = self.template_repo.list(platform=destination.platform, active=True, limit=1)
        return matches[0] if matches else None

    def _resolve_template_for_destination(
        self, destination: Destination, forced_template: Optional[PostTemplate]
    ) -> tuple[Optional[PostTemplate], Optional[str]]:
        """Returns (template, error) — exactly one is None. Shared by
        generate_posts and create_queue so the platform-matching/auto-select
        rule exists in one place."""
        if forced_template is not None:
            if forced_template.platform != destination.platform:
                return None, (
                    f"Template '{forced_template.name}' is for "
                    f"{forced_template.platform.value}, but destination "
                    f"'{destination.name}' is {destination.platform.value} — skipped"
                )
            return forced_template, None

        template = self._auto_select_template(destination)
        if template is None:
            return None, (
                f"No active {destination.platform.value} template found — "
                f"skipped '{destination.name}'"
            )
        return template, None

    def generate_posts(
        self, job_id: int, destination_ids: list[int], template_id: Optional[int] = None
    ) -> tuple[list[Post], list[str]]:
        job = self.job_repo.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")

        forced_template: Optional[PostTemplate] = None
        if template_id is not None:
            forced_template = self.template_repo.get(template_id)
            if forced_template is None:
                raise NotFoundError(f"Template {template_id} not found")

        variables = job_to_variables(job)
        created: list[Post] = []
        errors: list[str] = []

        for destination_id in destination_ids:
            destination = self.destination_repo.get(destination_id)
            if destination is None:
                errors.append(f"Destination {destination_id} not found — skipped")
                continue

            template, error = self._resolve_template_for_destination(destination, forced_template)
            if error:
                errors.append(error)
                continue

            content = render_template(template.template_text, variables)
            post = self.repo.create(
                job_id=job_id,
                destination_id=destination_id,
                template_id=template.id,
                content=content,
                status=PostStatus.DRAFT,
            )
            created.append(post)

        return created, errors

    def generate_variations(
        self, job_id: int, destination_id: int, template_ids: list[int]
    ) -> tuple[list[Post], list[str]]:
        """Same job + same destination, multiple templates — lets the
        recruiter compare tones (professional/short/urgent/...) side by
        side before picking one to actually use."""
        job = self.job_repo.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        destination = self.destination_repo.get(destination_id)
        if destination is None:
            raise NotFoundError(f"Destination {destination_id} not found")

        variables = job_to_variables(job)
        created: list[Post] = []
        errors: list[str] = []

        for template_id in template_ids:
            template = self.template_repo.get(template_id)
            if template is None:
                errors.append(f"Template {template_id} not found — skipped")
                continue
            if template.platform != destination.platform:
                errors.append(
                    f"Template '{template.name}' is for {template.platform.value}, "
                    f"but destination is {destination.platform.value} — skipped"
                )
                continue

            content = render_template(template.template_text, variables)
            post = self.repo.create(
                job_id=job_id,
                destination_id=destination_id,
                template_id=template.id,
                content=content,
                status=PostStatus.DRAFT,
            )
            created.append(post)

        return created, errors

    # --- Phase 6: Queue ---------------------------------------------------

    def _spam_protection_warnings(self, destination: Destination, target_date) -> list[str]:
        """Section 19's internal workflow safeguards. These are warnings,
        not blocks — the post is still created either way. Deliberately
        not a hard stop: the recruiter might have a real reason to post
        again despite a cooldown (e.g. an urgent update), and this is a
        self-imposed workflow control, not a platform restriction to
        enforce against the user."""
        warnings: list[str] = []

        if not destination.active:
            warnings.append(f"'{destination.name}' is inactive")

        if destination.min_posting_interval_minutes and destination.last_posted_at:
            earliest_next = destination.last_posted_at + timedelta(
                minutes=destination.min_posting_interval_minutes
            )
            if utcnow() < earliest_next:
                warnings.append(
                    f"'{destination.name}' has a {destination.min_posting_interval_minutes}-minute "
                    f"cooldown and was last posted to at {destination.last_posted_at:%Y-%m-%d %H:%M}"
                )

        if destination.daily_posting_limit:
            count = self.repo.count_for_destination_on_date(destination.id, target_date)
            if count >= destination.daily_posting_limit:
                warnings.append(
                    f"'{destination.name}' already has {count} post(s) for "
                    f"{target_date:%Y-%m-%d}, at or over its daily limit of "
                    f"{destination.daily_posting_limit}"
                )

        existing_queued = self.repo.list(
            job_id=None, destination_id=destination.id, status=PostStatus.QUEUED, limit=1
        )
        if existing_queued:
            warnings.append(f"'{destination.name}' already has a queued post — this would be a duplicate")

        return warnings

    def create_queue(
        self,
        job_id: int,
        destination_ids: list[int],
        template_id: Optional[int] = None,
        start_at: Optional[datetime] = None,
        delay_minutes: int = 5,
    ) -> tuple[list[Post], list[str], list[str]]:
        """Section 31's batch queue creation: one job, many destinations
        (potentially 50+10+1 across platforms), a posting window. Each
        destination gets its own staggered scheduled_at
        (start_at + index * delay_minutes) and status=Queued, not Draft —
        that's the difference from generate_posts.

        Returns (created, errors, warnings). errors are hard skips (no
        valid post could be produced at all); warnings are Section 19
        spam-protection flags that don't prevent the post from being
        created.
        """
        job = self.job_repo.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")

        forced_template: Optional[PostTemplate] = None
        if template_id is not None:
            forced_template = self.template_repo.get(template_id)
            if forced_template is None:
                raise NotFoundError(f"Template {template_id} not found")

        start = start_at or utcnow()
        variables = job_to_variables(job)
        created: list[Post] = []
        errors: list[str] = []
        warnings: list[str] = []
        slot = 0

        # dict.fromkeys preserves order while dropping accidental duplicate
        # destination ids in the request — not worth a warning, just noise.
        for destination_id in dict.fromkeys(destination_ids):
            destination = self.destination_repo.get(destination_id)
            if destination is None:
                errors.append(f"Destination {destination_id} not found — skipped")
                continue

            template, error = self._resolve_template_for_destination(destination, forced_template)
            if error:
                errors.append(error)
                continue

            scheduled_at = start + timedelta(minutes=delay_minutes * slot)
            warnings.extend(self._spam_protection_warnings(destination, scheduled_at.date()))

            content = render_template(template.template_text, variables)
            post = self.repo.create(
                job_id=job_id,
                destination_id=destination_id,
                template_id=template.id,
                content=content,
                status=PostStatus.QUEUED,
                scheduled_at=scheduled_at,
            )
            created.append(post)
            slot += 1

        return created, errors, warnings

    def queue_existing_post(self, post_id: int, scheduled_at: Optional[datetime] = None) -> Post:
        """Promotes a single Draft post (e.g. one made via Post Creator)
        into the queue, rather than batch-creating new ones."""
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")
        if post.status != PostStatus.DRAFT:
            raise ValueError(f"Only a Draft post can be queued directly; this post is {post.status.value}")
        return self.repo.update(
            post_id, status=PostStatus.QUEUED, scheduled_at=scheduled_at or utcnow()
        )

    def start(self, post_id: int) -> Post:
        """Queued -> Processing (the manual path), and, since Phase 10,
        Scheduled -> Processing too — the ticker starting a due post is
        the same "actively being handled right now" transition as a human
        clicking Start, whichever one triggered it."""
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")
        if post.status not in (PostStatus.QUEUED, PostStatus.SCHEDULED):
            raise ValueError(
                f"Only a Queued or Scheduled post can be started; this post is {post.status.value}"
            )
        return self.repo.update(post_id, status=PostStatus.PROCESSING)

    def schedule(self, post_id: int) -> Post:
        """Queued -> Scheduled: the explicit opt-in into Phase 10's
        unattended sending, deliberately separate from Queued itself (see
        PROJECT_STATUS.md section 18) — a post can have a scheduled_at
        time and still need a human to trigger it (Start/Send); Scheduled
        specifically means "the ticker should act on this without anyone
        watching," which not every Queued post should default to."""
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")
        if post.status != PostStatus.QUEUED:
            raise ValueError(f"Only a Queued post can be scheduled; this post is {post.status.value}")
        if post.scheduled_at is None:
            raise ValueError("Can't schedule a post with no scheduled_at time")
        return self.repo.update(post_id, status=PostStatus.SCHEDULED)

    def unschedule(self, post_id: int) -> Post:
        """Scheduled -> Queued: reverses schedule() — the symmetric undo
        every other opt-in state in this project gets (paused has
        resume(), Failed has retry())."""
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")
        if post.status != PostStatus.SCHEDULED:
            raise ValueError(f"Only a Scheduled post can be unscheduled; this post is {post.status.value}")
        return self.repo.update(post_id, status=PostStatus.QUEUED)

    def skip(self, post_id: int) -> Post:
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")
        if post.status in (PostStatus.POSTED, PostStatus.SKIPPED):
            raise ValueError(f"Can't skip a post that's already {post.status.value}")
        return self.repo.update(post_id, status=PostStatus.SKIPPED)

    def retry(self, post_id: int) -> Post:
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")
        if post.status != PostStatus.FAILED:
            raise ValueError(f"Only a Failed post can be retried; this post is {post.status.value}")
        return self.repo.update(post_id, status=PostStatus.QUEUED, error_message=None)

    def set_paused(self, post_id: int, paused: bool) -> Post:
        post = self.repo.update(post_id, paused=paused)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")
        return post

    def progress(self, job_id: Optional[int] = None) -> dict:
        """Section 43's 'show campaign progress' — post counts by status,
        optionally scoped to one job."""
        counts = {status.value: self.repo.count(job_id=job_id, status=status) for status in PostStatus}
        return {"counts": counts, "total": sum(counts.values())}

    # --- Phase 7: Facebook Assistant ---------------------------------------
    #
    # Section 13/40's sequential, one-group-at-a-time workflow. Reuses
    # Post.status (Queued -> Processing, exactly like Phase 6's start())
    # rather than inventing new statuses — "which post is currently being
    # handled" is a real, durable fact worth keeping if the page reloads
    # mid-flow. What's deliberately NOT persisted here is the assistant's
    # position/ordering through the list — that lives in the frontend page's
    # session state (see frontend/pages/6_Facebook_Assistant.py), since it's
    # only ever "which ones has this browser tab looked at so far," not a
    # fact about the post itself.

    def facebook_assist_candidates(self) -> list[Post]:
        """Facebook posts eligible for the assistant right now: Queued (not
        yet engaged) or Processing-and-not-paused (the one currently being
        handled — included so reloading the page resumes it instead of
        losing it). A paused Processing post is deliberately excluded: the
        user set it aside via the Pause button and it's the Queue page's
        Resume action, not this list, that brings it back.

        Two separate status-filtered queries rather than one big fetch plus
        a limit, so a large backlog of already-Posted/Skipped Facebook posts
        can never crowd real candidates out of a truncated result.
        """
        queued = self.repo.list(platform=Platform.FACEBOOK, status=PostStatus.QUEUED, limit=500)
        processing = self.repo.list(platform=Platform.FACEBOOK, status=PostStatus.PROCESSING, limit=500)
        candidates = queued + [p for p in processing if not p.paused]
        candidates.sort(key=lambda p: (p.scheduled_at is None, p.scheduled_at, p.created_at))
        return candidates

    def start_facebook_assist(self, post_id: int) -> tuple[Post, bool, bool]:
        """Engages a Facebook post: transitions Queued -> Processing (via
        the same start() validation Phase 6 uses) if it isn't already
        Processing, then opens the destination's URL in the user's browser
        and copies the content to the OS clipboard.

        Safe to call again on a post that's already Processing (e.g. the
        page was reloaded mid-flow) — it re-opens/re-copies without
        re-validating the Queued->Processing transition a second time.

        Returns (post, browser_opened, clipboard_copied). The two booleans
        reflect whether each OS-level action actually succeeded — a Linux
        box without xclip/xsel, or a destination with no URL, fails one or
        both without that being a reason to fail the whole request; the
        Facebook Assistant page falls back to its own copy button and
        "Open destination" link when either is False.
        """
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")

        destination = self.destination_repo.get(post.destination_id)
        if destination is None or destination.platform != Platform.FACEBOOK:
            raise ValueError("The Facebook Assistant only works with Facebook destinations")

        if post.status in (PostStatus.QUEUED, PostStatus.SCHEDULED):
            post = self.start(post_id)
        elif post.status != PostStatus.PROCESSING:
            raise ValueError(
                f"Only a Queued, Scheduled, or already-in-progress (Processing) post can use "
                f"the Facebook Assistant; this post is {post.status.value}"
            )

        browser_opened = open_destination(destination.url)
        clipboard_copied = copy_content(post.content)
        return post, browser_opened, clipboard_copied

    def mark_posted(self, post_id: int, external_post_id: Optional[str] = None) -> Post:
        """Marks a Processing post Posted and stamps posted_at — the first
        place in the codebase either PostStatus.POSTED or Post.posted_at
        actually gets set. Also stamps the destination's last_posted_at, so
        Section 19's cooldown/daily-limit checks (which read that field)
        become accurate the moment a real post happens, not just in theory.

        external_post_id is optional (Phase 7's Facebook flow has no such
        id and omits it) — Phase 8's Telegram send passes Telegram's own
        message_id here in the same call, rather than a second update.
        """
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")
        if post.status != PostStatus.PROCESSING:
            raise ValueError(f"Only a Processing post can be marked Posted; this post is {post.status.value}")

        fields: dict = {"status": PostStatus.POSTED, "posted_at": utcnow()}
        if external_post_id is not None:
            fields["external_post_id"] = external_post_id
        updated = self.repo.update(post_id, **fields)
        self.destination_repo.update(post.destination_id, last_posted_at=utcnow())
        return updated

    def mark_failed(self, post_id: int, error_message: Optional[str] = None) -> Post:
        """Marks a Processing post Failed. A blank/omitted reason still
        records a non-empty error_message — an empty Failed reason reads as
        a missing feature next time someone looks at the Queue page, not as
        "nothing went wrong." Already-Failed posts go back to Queued via the
        existing retry(), not through this method."""
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")
        if post.status != PostStatus.PROCESSING:
            raise ValueError(f"Only a Processing post can be marked Failed; this post is {post.status.value}")

        message = error_message.strip() if error_message and error_message.strip() else "Marked Failed manually"
        return self.repo.update(post_id, status=PostStatus.FAILED, error_message=message)

    # --- Phase 8: Telegram ---------------------------------------------
    #
    # Unlike Facebook, sending a Telegram post needs no human step — the
    # Bot API either accepts it or it doesn't, immediately. So this one
    # method does the whole thing (Start, call the Bot API, record the
    # outcome) rather than splitting into an "engage" step plus separate
    # terminal-outcome calls the way Facebook's assistant does. It reuses
    # mark_posted()/mark_failed() from Phase 7 rather than duplicating
    # their Processing-only validation — exactly the reuse Phase 7's
    # write-up (section 14) called out as the reason those two methods
    # were kept platform-agnostic.

    def send_telegram_post(self, post_id: int) -> Post:
        """Sends a Telegram post via the Bot API and immediately resolves
        it to Posted (with Telegram's message_id captured as
        external_post_id) or Failed (with Telegram's own error, or a
        network/config problem) — there's no separate "engage" step to
        call first the way there is for Facebook."""
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")

        destination = self.destination_repo.get(post.destination_id)
        if destination is None or destination.platform != Platform.TELEGRAM:
            raise ValueError("send_telegram_post only works with Telegram destinations")

        if post.status in (PostStatus.QUEUED, PostStatus.SCHEDULED):
            post = self.start(post_id)
        elif post.status != PostStatus.PROCESSING:
            raise ValueError(
                f"Only a Queued, Scheduled, or already-in-progress (Processing) post can be "
                f"sent; this post is {post.status.value}"
            )

        bot_token = get_settings().telegram_bot_token
        success, message_id, error = send_message(bot_token, destination.external_id, post.content)

        if success:
            return self.mark_posted(post_id, external_post_id=message_id)
        return self.mark_failed(post_id, error)

    # --- Phase 9: TikTok -------------------------------------------------
    #
    # TikTok defaults to PostingMethod.MANUAL (see
    # app/services/destination_service.py's _DEFAULT_POSTING_METHOD) —
    # audit-gated API access isn't something most users of this tool will
    # have, so there's no "engage"/"send" method here the way Facebook and
    # Telegram have. This is purely a content-prep step: it fills in
    # Post.media_path and leaves status untouched. Resolving a MANUAL post
    # to Posted/Failed once the recruiter has actually posted it by hand
    # goes through the same platform-agnostic mark_posted()/mark_failed()
    # from Phase 7 — see the Queue page's generic Processing-row buttons,
    # not a TikTok-specific method.

    def generate_tiktok_visual(self, post_id: int) -> Post:
        """Generates a recruitment graphic for a TikTok post and stores
        its path in Post.media_path — available any time before the post
        is Posted or Skipped, and safe to call again (each call overwrites
        the same file rather than accumulating old versions, so
        "regenerate" is just "generate" a second time)."""
        post = self.repo.get(post_id)
        if post is None:
            raise NotFoundError(f"Post {post_id} not found")

        destination = self.destination_repo.get(post.destination_id)
        if destination is None or destination.platform != Platform.TIKTOK:
            raise ValueError("generate_tiktok_visual only works with TikTok destinations")
        if post.status in (PostStatus.POSTED, PostStatus.SKIPPED):
            raise ValueError(f"Can't generate a visual for a {post.status.value} post")

        job = self.job_repo.get(post.job_id)
        if job is None:
            raise NotFoundError(f"Job {post.job_id} not found")

        output_path = Path(get_settings().media_dir) / f"post_{post_id}.png"
        generate_recruitment_visual(
            job_title=job.title,
            company=job.company,
            location=job.location,
            salary_text=job.salary_text,
            output_path=str(output_path),
        )
        return self.repo.update(post_id, media_path=str(output_path))
