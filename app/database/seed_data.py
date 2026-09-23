# Default starter Post Templates.
#
# These are seeded once, only when the templates table is empty, so the app
# has useful templates out of the box without overwriting anything the
# recruiter has created or edited.
#
# The defaults cover the different platform formats:
# Facebook gets a detailed post, Telegram gets a compact version, and
# TikTok gets a short version with hashtags.
#
# They also include several variation types such as Professional, Urgent,
# Fresh Graduates, Arabic, and Bilingual. The Telegram template covers the
# Short/compact variation.
#
# The templates are fully editable and can be deleted. Once any template
# exists, the defaults are not seeded again.
#
# The Bilingual template uses bilingual labels around the recruiter's
# existing content. It does not generate separate English and Arabic
# versions because each Job only has one requirements/description field.
# For fully separate wording, use the English and Arabic templates instead.
from sqlalchemy.orm import Session

from app.database.enums import Platform
from app.database.models import PostTemplate

_DEFAULT_TEMPLATES = [
    {
        "name": "Facebook — Professional / Detailed (English)",
        "platform": Platform.FACEBOOK,
        "language": "English",
        "template_text": (
            "🔷 WE ARE HIRING: {{job_title}} 🔷\n\n"
            "📍 Location: {{location}}\n"
            "🏢 Company: {{company}}\n"
            "💰 Salary: {{salary}}\n"
            "⏰ Employment Type: {{employment_type}}\n"
            "📋 Experience: {{experience}}\n\n"
            "✅ Requirements:\n{{requirements}}\n\n"
            "🎁 Benefits:\n{{benefits}}\n\n"
            "📩 How to apply: {{application_method}}\n"
            "🔗 {{application_url}}"
        ),
    },
    {
        "name": "Facebook — Detailed (Arabic)",
        "platform": Platform.FACEBOOK,
        "language": "Arabic",
        "template_text": (
            "🔷 مطلوب: {{job_title}} 🔷\n\n"
            "📍 الموقع: {{location}}\n"
            "🏢 الشركة: {{company}}\n"
            "💰 الراتب: {{salary}}\n"
            "⏰ نوع الوظيفة: {{employment_type}}\n\n"
            "✅ المتطلبات:\n{{requirements}}\n\n"
            "🎁 المميزات:\n{{benefits}}\n\n"
            "📩 للتقديم: {{application_method}}\n"
            "🔗 {{application_url}}"
        ),
    },
    {
        "name": "Facebook — Urgent Hiring (English)",
        "platform": Platform.FACEBOOK,
        "language": "English",
        "template_text": (
            "🚨 URGENT HIRING — {{job_title}} 🚨\n\n"
            "{{company}} needs someone NOW for this role!\n\n"
            "📍 {{location}} | 💰 {{salary}}\n"
            "⏰ Start ASAP\n\n"
            "✅ Requirements:\n{{requirements}}\n\n"
            "Don't wait — apply today:\n"
            "🔗 {{application_url}}\n"
            "📩 {{application_method}}"
        ),
    },
    {
        "name": "Facebook — Fresh Graduates (English)",
        "platform": Platform.FACEBOOK,
        "language": "English",
        "template_text": (
            "🎓 FRESH GRADUATES WELCOME — {{job_title}} 🎓\n\n"
            "{{company}} is looking for motivated new graduates to join the team!\n\n"
            "📍 {{location}} | 💰 {{salary}}\n"
            "📋 No prior experience required\n\n"
            "🎁 What you'll get:\n{{benefits}}\n\n"
            "Ready to start your career? Apply now:\n"
            "🔗 {{application_url}}"
        ),
    },
    {
        "name": "Facebook — Bilingual",
        "platform": Platform.FACEBOOK,
        "language": "Bilingual",
        "template_text": (
            "{{job_title}} — {{company}}\n"
            "وظيفة: {{job_title}} في {{company}}\n\n"
            "📍 Location / الموقع: {{location}}\n"
            "💰 Salary / الراتب: {{salary}}\n\n"
            "{{requirements}}\n\n"
            "Apply / للتقديم: {{application_url}}"
        ),
    },
    {
        "name": "Telegram — Compact / Short (English)",
        "platform": Platform.TELEGRAM,
        "language": "English",
        "template_text": (
            "🔹 {{job_title}} — {{company}}\n"
            "📍 {{location}} | 💰 {{salary}}\n\n"
            "{{requirements}}\n\n"
            "Apply: {{application_url}}"
        ),
    },
    {
        "name": "TikTok — Short + hashtags (English)",
        "platform": Platform.TIKTOK,
        "language": "English",
        "template_text": (
            "We're hiring! {{job_title}} at {{company}} 🚀\n"
            "📍 {{location}} | 💰 {{salary}}\n"
            "Apply now 👉 {{application_url}}\n\n"
            "#hiring #jobs #careers"
        ),
    },
]


def seed_default_templates(db: Session) -> None:
    if db.query(PostTemplate).count() > 0:
        return  # never re-seed once any template exists, default or custom
    for data in _DEFAULT_TEMPLATES:
        db.add(PostTemplate(**data))
    db.commit()
