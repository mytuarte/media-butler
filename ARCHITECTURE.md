# Media Butler Architecture

## Design Goals

Media Butler should remain easy to understand.

Architecture should only become more complex when there is a clear benefit.

---

# Layers

Discord

↓

Commands

↓

Services

↓

Models

↓

External APIs

---

# Commands

Commands orchestrate work.

Commands should contain very little business logic.

Good:

results = radarr.search(query)

Bad:

requests.get(...)

Commands should never know:

- API URLs
- API Keys
- HTTP requests
- JSON parsing

Commands ask services to perform work.

---

# Services

Each service owns one external system.

Examples:

DiscordService

Owns Discord.

RadarrService

Owns Radarr.

SonarrService

Owns Sonarr.

OverseerrService

Owns Overseerr.

Services are allowed to understand:

- HTTP
- JSON
- Authentication
- External APIs

Services should never know Discord exists.

---

# Models

Models carry data.

Models should never generate Discord embeds.

Models should never perform HTTP requests.

Current models:

MovieNotification

MediaResult

---

# Views (Planned)

Future Discord UI components will live in:

views/

Examples:

SearchResultsView

DeleteConfirmationView

MovieDetailsView

Views own:

- Discord embeds
- Buttons
- Dropdowns
- Interaction callbacks

Commands should not build complex Discord UI.

---

# Current Flow

Discord

↓

DiscordService

↓

CommandService

↓

FindCommand

↓

RadarrService

↓

MediaResult

↓

Discord

---

# Design Principles

Commands orchestrate.

Services perform work.

Models carry data.

Views own presentation.

---

# Dependency Direction

Commands

↓

Services

↓

Models

Never the opposite.

Services should not depend on Commands.

Models should not depend on Services.

---

# Current Folder Structure

src/

commands/
models/
services/

Future:

views/

---

# Future Architecture

Discord

↓

Commands

↓

Services

↓

Models

↓

Views

↓

Discord

---

# Search Feature

Current:

!find

↓

RadarrService.search()

↓

MediaResult[]

↓

Discord Embed

Future:

!find

↓

RadarrService.search()

SonarrService.search()

↓

Combined MediaResult[]

↓

SearchResultsView

↓

Discord Buttons

---

# Current Philosophy

Prefer vertical slices.

Finish one complete feature before starting another.

Example:

Search

↓

Search UI

↓

Search Buttons

↓

Delete

instead of

Search

↓

Sonarr

↓

Overseerr

↓

Delete

This keeps every completed feature usable.