# AI_GUIDELINES.md

## Purpose

This document defines the development rules for Media Butler.

The project has been intentionally designed to remain simple, understandable, and easy to maintain. AI assistants should preserve that philosophy.

---

# Primary Rule

**Do not perform architectural rewrites unless explicitly requested.**

If a significantly different architecture appears beneficial, explain the proposal first and wait for approval before making changes.

---

# Development Philosophy

* Make the smallest change necessary.
* Preserve the existing architecture.
* Favor readability over cleverness.
* Avoid introducing abstractions until they solve a real problem.
* Build one complete feature at a time.
* Keep commits feature-focused.

---

# Architecture

The project follows a layered architecture.

Discord

↓

Commands

↓

Services

↓

Models

↓

External APIs

Future Discord UI components belong in:

views/

Maintain this dependency direction.

Never introduce dependencies that reverse these layers.

---

# Commands

Commands orchestrate work.

Commands should:

* Validate input.
* Call services.
* Coordinate workflow.
* Return results.

Commands should **not**:

* Perform HTTP requests.
* Parse JSON.
* Know API URLs.
* Know API keys.
* Build complex Discord UI.

---

# Services

Each service owns one external system.

Examples:

* DiscordService
* RadarrService
* SonarrService
* OverseerrService

Services may:

* Perform HTTP requests.
* Parse JSON.
* Authenticate.
* Handle API-specific behavior.

Services should remain independent of Discord commands.

---

# Models

Models carry data.

Models should remain lightweight.

Models should not:

* Perform HTTP requests.
* Generate Discord embeds.
* Contain Discord interaction logic.

---

# Views

Future Discord embeds, buttons, dropdowns, and interaction callbacks belong in:

views/

Presentation should remain separate from business logic.

---

# Coding Style

When modifying code:

* Prefer extending existing classes over replacing them.
* Keep functions focused.
* Avoid unnecessary refactoring.
* Preserve existing naming conventions.
* Match the current coding style.

If a file is modified, prefer returning the complete file unless only a very small change is requested.

---

# Development Workflow

For every feature:

1. Implement.
2. Test locally.
3. Review.
4. Commit.
5. Push.
6. Deploy to the NAS.

Do not skip local testing before deployment.

---

# Git

Use feature branches.

Commit messages should describe completed features rather than implementation details.

Good:

* Add media search feature
* Add Discord search buttons

Avoid:

* Refactor helper method
* Rename variable

---

# AI Behavior

When assisting:

* Preserve the current architecture.
* Avoid speculative improvements.
* Avoid introducing new frameworks.
* Avoid rewriting working code.
* Explain the reasoning behind significant changes.
* Ask questions when requirements are ambiguous.

Incremental improvement is preferred over large redesigns.

The existing project structure is the source of truth.
