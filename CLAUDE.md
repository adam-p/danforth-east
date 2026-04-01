# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Membership management system for the Danforth East Community Association. Uses Google Sheets as the primary database (for human accessibility) instead of a traditional database. Deployed on Google App Engine.

## Commands

```bash
# Install dependencies
poetry install

# Run locally
flask run

# Run tests
poetry run pytest tests/ -v

# Lint
pylint *.py

# Deploy to App Engine
gcloud app deploy
gcloud app deploy cron.yaml   # deploy cron schedule separately
```

There is no automated test suite. Testing is manual via the web UI; PayPal flows use PayPal's sandbox.

## Architecture

Flask application using Google Cloud Platform services throughout:

- **Google Sheets** — primary data store (members, volunteers, authorized users, volunteer interests, skill categories). `sheetdata.py` is a low-level Sheets API wrapper; `gapps.py` contains business logic built on top of it.
- **Google NDB (Cloud Datastore)** — temporary storage for in-flight self-serve registrations (pending PayPal payment confirmation).
- **Google Cloud Tasks** — async task queue for email sending, archival, and cleanup (handlers in `tasks.py`).
- **Google Sign-In / Flask-Login** — admin authentication, validated against an "Authorized Users" spreadsheet (`auth.py`).
- **PayPal IPN** — payment processing for public self-registration (`self_serve.py`).
- **SMTP / MailChimp** — outbound email (`emailer.py`, `mailchimp.py`).

### Key flows

**Public registration (self-serve, iframe-embedded):**
`self_serve.py` → creates PayPal URL & stores pending member in NDB → user pays via PayPal → IPN callback validates payment → Cloud Task moves member to Sheets and sends welcome email.

**Admin registration:**
Admin authenticates via Google Sign-In → `admin_site.py` handles new-member/renewal forms → member written directly to Sheets → Cloud Task sends welcome email.

**Scheduled tasks (`cron.yaml`):**
- Archive previous year's member sheet (monthly)
- Delete expired NDB member candidates (daily)
- Send renewal reminder emails (daily)
- Sync MailChimp list (daily)

### Module responsibilities

| File | Role |
|------|------|
| `main.py` | Flask app init, blueprint registration, CSRF setup |
| `admin_site.py` | Admin routes: new member, renewal, authorization management |
| `self_serve.py` | Public registration form and PayPal IPN handler |
| `auth.py` | Google Sign-In integration, Flask-Login user loader |
| `tasks.py` | Cloud Tasks / cron handlers |
| `gapps.py` | Core business logic: member CRUD, spreadsheet operations |
| `sheetdata.py` | Low-level Google Sheets API CRUD wrapper |
| `emailer.py` | SMTP email sending |
| `mailchimp.py` | MailChimp list sync |
| `helpers.py` | Geocoding, address utilities |
| `utils.py` | Validation helpers (email, lat/long, etc.) |
| `config/__init__.py` | Field definitions, spreadsheet schemas, validation metadata |
| `config/private.py` | Secrets/credentials — not in repo; use `private.py.sample` as template |

## Configuration

All spreadsheet schema, field definitions, and validation rules live in `config/__init__.py`. Private credentials (API keys, spreadsheet IDs, SMTP settings) go in `config/private.py` (excluded from repo; see `config/private.py.sample`).

`app.yaml` configures App Engine (runtime Python 3.12, instance class F4, max 2 instances, HTTPS-only).
