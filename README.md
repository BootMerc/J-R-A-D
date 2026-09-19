<div align="center">
    
# J-R-A-D  
## 📋 Jobs & Recruitment Automation Dashboard
# STILL IN DEVELOPMENT
### PHASE 11/14

**A locally-hosted tool that distributes job postings across Facebook, Telegram, and TikTok — automating what platforms actually let you automate, and honestly assisting with what they don't.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](docs/SETUP.md)
[![Tests](https://img.shields.io/badge/tests-30(so%20far)%20passing-brightgreen)](docs/SETUP.md#running-tests)
[![Cost](https://img.shields.io/badge/cost-%240-success)](#-what-it-costs)

[Overview](#-overview) • [Features](#-features) • [Screenshots](#-Screenshots) • [Architecture](#-architecture) • [Engineering Highlights](#-engineering-highlights) • [Getting Started](#-getting-started)

</div>
<div align="center">

## this will be built phase by phase, with a real test.

</div>
---

## 📖 Overview

A recruiter posting **50-100 job ads a day** across social platforms spends most of that time on repetitive, mechanical work: rewriting the same job for different audiences, copy-pasting into browser tabs, tracking what's been posted where. This project automates the parts that can honestly be automated, and builds a fast, guided workflow for the parts that can't — **without bypassing any platform's rate limits, terms of service, or bot detection.**

It's a full-stack local application: a **FastAPI** backend, a **Streamlit** frontend, a **SQLite** database, and three real platform integrations, built in 14 planned phases plus a round of post-launch polish. Everything in this README is real — the diagrams describe the actual code, the numbers come from actually running the test suite, and the "Engineering Highlights" section documents real bugs that were actually found and fixed, not a fabricated case study.

---

## ✨ Features

| | Feature | What it does |
|---|---|---|
| 📋 | **Job Management** | Create, search, filter, close, and archive job postings |
| 🎯 | **Destinations** | Manage target groups/channels/accounts, with tags, categories, and CSV import/export |
| 📝 | **Templates** | 7 platform-tuned templates seeded automatically, with `{{variable}}` rendering and live preview |
| ✍️ | **Post Creator** | Generate posts (and tone variations) from a job + template combination, auto-selecting the right template per platform |
| 📬 | **Queue** | Batch-queue posts across many destinations with staggered scheduling, plus a one-click **"queue all"** for existing drafts |
| 🖱️ | **Facebook Assistant** | A guided, one-group-at-a-time workflow: opens the browser, copies the post to your clipboard, you click Post — with keyboard shortcuts |
| ✈️ | **Telegram** | Fully automatic sending via the official Bot API — one click, done |
| 🎵 | **TikTok Visuals** | Generates a recruitment graphic (Pillow) with **verified-correct Arabic right-to-left text** — see below |
| 🗓️ | **Scheduler + Calendar** | A background ticker that actually sends due Telegram posts unattended, and a week-at-a-glance calendar view |
| 📊 | **Analytics** | Manually-logged funnel metrics (views → clicks → applications → hires), broken down by destination and by template |
| 💾 | **Backup/Restore** | One-command database backups with automatic retention, and a safety-net backup taken before every restore |

---

## 🤖 What's Actually Automated (and What Isn't)

Not every platform lets you automate posting — and pretending otherwise is how projects end up violating terms of service or getting accounts banned. Here's the honest breakdown:

| Platform | Automation level | How it actually works |
|---|:---:|---|
| ✈️ **Telegram** | 🟢 **Fully automatic** | Real HTTPS calls to Telegram's official Bot API. One click sends the post and records the real outcome. |
| 📘 **Facebook** | 🟡 **Browser-assisted** | Facebook has no public API for group posting. The app opens the group in *your* logged-in browser and copies the text to your clipboard — you paste and click Post. Nothing scripts a click on Facebook's own page. |
| 🎵 **TikTok** | 🔴 **Manual, by design** | TikTok's real posting API requires an app audit most individual developers won't get quickly. The app generates the recruitment graphic; you post it from your phone. |

No CAPTCHA solving. No stealth automation. No bypassing rate limits. If a platform doesn't support something, the app tells you and gives you a fast manual path instead of faking it.

---

## 🖼️ Screenshots

### Real system output: the TikTok visual generator

These aren't mockups — they're the actual PNG files this project's `visual_generator.py` produces.
<table>
<tr>
<td width="50%" align="center">

**English**

<img src="docs/images/tiktok-visual-english.png" width="280" alt="Generated recruitment visual, English"/>

</td>
<td width="50%" align="center">

**Arabic (right-to-left)**

<img src="docs/images/tiktok-visual-arabic.png" width="280" alt="Generated recruitment visual, Arabic"/>

</td>
</tr>
</table>

The Arabic version is the harder engineering problem than it looks — see [Engineering Highlights](#-engineering-highlights) below for why Pillow's *automatic* Arabic text handling can't be trusted on Windows, and how this was actually verified rather than assumed.

<details>
<summary><b>📸 App screenshots</b></summary>

<br>
The app has 8 pages — after running it locally (see [Getting Started](#-getting-started)), drop screenshots into `docs/images/` and reference them here:

![Dashboard](docs/images/dashboard.png)
![Queue page](docs/images/queue.png)
![Facebook Assistant](docs/images/facebook-assistant.png)


</details>

---


## 🏗️ Architecture

```mermaid
graph TB
    User(["👤 Recruiter"])
    
    subgraph Frontend["Streamlit Frontend — 8 pages"]
        UI["Jobs · Destinations · Templates · Post Creator<br/>Queue · Facebook Assistant · Calendar · Analytics"]
    end
    
    subgraph Backend["FastAPI Backend — 55 endpoints"]
        API["Repository → Service → API layers"]
        SCHED["⏱️ Background Scheduler<br/>(APScheduler)"]
    end
    
    DB[("🗄️ SQLite<br/>6 tables")]
    
    subgraph Integrations["Platform Integrations"]
        FB["📘 Facebook<br/>webbrowser + clipboard"]
        TG["✈️ Telegram<br/>Bot API (httpx)"]
        TT["🎵 TikTok<br/>Pillow visual generator"]
    end

    User -->|"HTTP :8501"| UI
    UI -->|"HTTP :8000"| API
    API --> DB
    SCHED -.->|"checks every 60s"| DB
    API --> FB
    API --> TG
    API --> TT
    SCHED ==>|"auto-sends due posts"| TG
    
    FB -.->|"you click Post"| FBWeb(["facebook.com"])
    TG ==>|"fully automated"| TGWeb(["Telegram servers"])
    TT -.->|"you post from your phone"| TTWeb(["TikTok app"])

    style TG fill:#0088cc,color:#fff
    style FB fill:#8b8b8b,color:#fff
    style TT fill:#8b8b8b,color:#fff
    style DB fill:#003b57,color:#fff
    style SCHED fill:#ffa726,color:#000
```

Solid arrows (`==>`) are fully automated; dashed arrows (`-.->`) are the human-in-the-loop steps — deliberately, not as a limitation
