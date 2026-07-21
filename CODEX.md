# Media Butler - Codex Instructions

## Project Overview

Media Butler is a Python Discord bot designed to assist with managing a personal media server ecosystem.

It integrates with:

- Plex
- Radarr
- Sonarr
- Overseerr
- SABnzbd
- Discord

The purpose is NOT to replace existing media request workflows.

Media requests continue to flow through Plex Watchlists.

Media Butler exists to:

- Provide media discovery
- Inspect library status
- Show download/request status
- Monitor system health
- Assist with media management
- Provide Discord-based visibility into the media pipeline

---

# Core Architecture Rules

Follow this architecture:


Discord
|
Commands
|
Command Services
|
Domain Services
|
Models
|
External APIs


Formatting:


Services
|
Views
|
Discord Embeds


---

# Design Philosophy

Keep the project simple.

Do NOT create unnecessary enterprise architecture.

Rules:

- Do not create abstractions until there are at least two real implementations.
- Prefer simple functions/classes over frameworks.
- Avoid unnecessary dependency injection.
- Avoid generic factories.
- Avoid "future proofing" without a current need.
- Keep code readable.

The goal is maintainable personal software, not a commercial SaaS platform.

---

# Code Organization

## Commands

Commands should:

- Receive Discord input
- Validate user input
- Call services
- Return results

Commands should NOT contain:

- API calls
- Business logic
- Data transformations

---

## Services

Services own business logic.

Examples:


services/
radarr_service.py
sonarr_service.py
overseerr_service.py
pipeline_monitor_service.py
health_monitor_service.py


Services should:

- Communicate with APIs
- Transform data
- Apply business rules

Services should NOT:

- Build Discord embeds
- Know Discord formatting

---

## Models

Models represent application data.

Use dataclasses where appropriate.

Prefer:

```python
MediaResult
HealthIssue
SeasonStatus
MonitoringState

over passing raw API dictionaries throughout the application.

External JSON should be converted into models at service boundaries.

Views

Views are responsible for Discord formatting.

Examples:

views/
    movie_details_view.py
    series_details_view.py
    health_alert_view.py

Views should:

Build embeds
Format user-facing output

Views should NOT:

Query APIs
Contain business logic
Existing Media Butler Architecture

Current flow:

Discord
 |
CommandService
 |
FindCommand
 |
MediaService
 |
RadarrSearchService
SonarrSearchService
OverseerrService
 |
MediaResult
 |
PipelineResolver
 |
PipelineMessageBuilder
 |
Discord Views

Do not redesign this architecture without discussion.

Media Request Philosophy

IMPORTANT:

Media Butler does NOT directly request media.

Do not add:

Request buttons
Direct Overseerr request commands
Radarr/Sonarr add commands

Requests must continue through:

Plex Watchlist
        |
        v
Overseerr
        |
        v
Radarr/Sonarr
Discord Rules

Discord-facing changes should:

Be clean
Be concise
Avoid unnecessary information

Hidden admin channels may contain:

Technical details
Debug information
Pipeline diagnostics

Public channels should contain:

User-friendly information only
Health Monitoring System

The health monitoring system monitors:

SABnzbd
Pipeline issues
Future services

Health alerts should:

Avoid duplicates
Persist through restarts
Only delete when an issue is confirmed resolved

Current behavior:

Issue detected
    |
    v
Create Discord alert
    |
    v
Save state

Issue remains
    |
    v
No duplicate

Issue resolved
    |
    v
Remove alert
Change Guidelines

Before modifying code:

Understand existing behavior.
Prefer minimal changes.
Do not rewrite working systems.
Preserve existing architecture.
Explain intended changes before applying large refactors.
Testing Requirements

After code changes:

Run:

Application startup
Relevant debug endpoint
Relevant Discord workflow

Do not assume success from code inspection alone.

Git Rules

Before committing:

Check:

git status

Review:

git diff

Commit messages should describe intent.

Examples:

Good:

Add persistent health alert state tracking

Bad:

Update files
Coding Style

Prefer:

Explicit code
Clear variable names
Small functions
Type hints
Readability

Avoid:

Clever one-liners
Excessive comments
Premature optimization
Current Development Priority

When choosing between options:

Prioritize:

Correct user-facing behavior
Reliability
Simplicity
Maintainability

Performance optimization is lower priority.

Working Agreement

The developer prefers:

Step-by-step guidance
Minimal unnecessary explanation
Complete file replacements when requested
Clear next actions
Testing after changes

Do not ask the developer to manually edit multiple locations when a full replacement file is practical.


---

## Transition steps

Do this in order:

### 1. Add the file

In VS Code:


Right click repo root
→ New File
→ CODEX.md
→ paste contents
→ save


---

### 2. Commit it

Run:

```powershell
git add CODEX.md
git commit -m "Add Codex project instructions"
git push