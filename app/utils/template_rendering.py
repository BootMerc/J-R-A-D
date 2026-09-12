"""Template {{variable}} substitution.

Deliberately a plain utility with no database access, not a method on
TemplateService — Phase 5's post generator needs the exact same
substitution logic (render a template against a job) and shouldn't have to
depend on TemplateService to get it.
"""

from __future__ import annotations

import re
from typing import Optional

from app.database.models import Job

_VARIABLE_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")

# Section 6's example list is "such as" — not exhaustive — so this covers
# every free-text/short Job field a recruiter could plausibly want in a
# post, not just the 8 explicitly named in the spec.
KNOWN_VARIABLES = [
    "job_title", "company", "location", "salary", "employment_type",
    "experience", "education", "language_requirements", "requirements",
    "responsibilities", "benefits", "working_hours", "application_method",
    "application_url", "contact_phone", "contact_whatsapp", "contact_email",
    "description",
]


def format_salary(
    salary_min: Optional[int], salary_max: Optional[int], salary_text: Optional[str]
) -> str:
    """salary_text wins if set (it's the recruiter's own wording, e.g.
    "Negotiable"). Otherwise falls back to formatting whatever of
    salary_min/salary_max is present."""
    if salary_text:
        return salary_text
    if salary_min and salary_max:
        return f"{salary_min:,} - {salary_max:,}"
    if salary_min:
        return f"{salary_min:,}+"
    if salary_max:
        return f"Up to {salary_max:,}"
    return ""


def job_to_variables(job: Job) -> dict[str, str]:
    """Maps a Job row to the {{variable}} names templates can reference.
    Missing fields become empty strings, not the literal "None"."""
    return {
        "job_title": job.title or "",
        "company": job.company or "",
        "location": job.location or "",
        "salary": format_salary(job.salary_min, job.salary_max, job.salary_text),
        "employment_type": job.employment_type or "",
        "experience": job.experience or "",
        "education": job.education or "",
        "language_requirements": job.language_requirements or "",
        "requirements": job.requirements or "",
        "responsibilities": job.responsibilities or "",
        "benefits": job.benefits or "",
        "working_hours": job.working_hours or "",
        "application_method": job.application_method or "",
        "application_url": job.application_url or "",
        "contact_phone": job.contact_phone or "",
        "contact_whatsapp": job.contact_whatsapp or "",
        "contact_email": job.contact_email or "",
        "description": job.description or "",
    }


def extract_variables(template_text: str) -> list[str]:
    """All distinct {{name}} placeholders referenced in a template,
    regardless of whether they're recognized."""
    return sorted(set(_VARIABLE_PATTERN.findall(template_text)))


def unknown_variables(template_text: str) -> list[str]:
    """Placeholders that won't resolve to anything — almost always a typo.
    Surfaced in the API/UI so it's caught before someone posts
    "{{sallary}}" to 50 Facebook groups."""
    used = set(extract_variables(template_text))
    return sorted(used - set(KNOWN_VARIABLES))


def render_template(template_text: str, variables: dict[str, str]) -> str:
    """Substitutes every recognized {{name}}. Unrecognized placeholders are
    left exactly as written rather than silently blanked — a visibly broken
    {{typo}} in the output is a better failure mode than text quietly
    missing a value."""

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))

    return _VARIABLE_PATTERN.sub(_replace, template_text)
