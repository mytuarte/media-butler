# Media Butler

## Overview

Media Butler is a Python application that integrates with Radarr, Sonarr, Overseerr, and Discord.

It has two primary responsibilities:

1. Receive webhook notifications from Radarr and Sonarr and send rich Discord notifications.
2. Provide an interactive Discord bot that allows users to search and manage media.

The application runs:

- Locally on Windows during development.
- Inside Docker on a UGREEN NAS for production.

---

# Current Technology

- Python 3.13
- Flask
- discord.py
- requests
- Docker
- GitHub

Development environment:

- VS Code
- GitHub Desktop
- Python virtual environment (.venv)

---

# Current Features

## Notifications

- Radarr webhook
- Sonarr webhook
- Rich Discord embeds
- Mention Discord user who requested media

## Discord Bot

- !ping
- !help
- !find

Commands are restricted to a private Discord admin channel.

---

# Current Workflow

Development always occurs locally.

Windows Laptop
    ↓
VS Code
    ↓
GitHub Desktop
    ↓
GitHub
    ↓
NAS Deployment

The NAS should only be updated after a feature has been completed and tested locally.

---

# Git Workflow

Feature branches are used.

Typical workflow:

1. Build one feature.
2. Test locally.
3. Commit.
4. Push.
5. Deploy to NAS.

Commits should describe features rather than implementation details.

Example:

Add media search feature

instead of

Added MediaResult class

---

# Current Project Structure

src/

commands/
models/
services/

config.py
main.py

---

# Current Commands

!ping

Tests Discord connectivity.

!help

Displays all registered commands.

!find

Searches the Radarr library.

(Currently Radarr only.)

---

# Development Philosophy

- Build one feature at a time.
- Test after every feature.
- Commit after every feature.
- Avoid introducing abstractions until they solve a real problem.
- Prefer simple code over clever code.

---

# Roadmap

Phase 1

- Improve !find
- Multiple search results
- Discord buttons
- Movie details

Phase 2

- Delete media
- Refresh media
- Monitor / Unmonitor

Phase 3

- Sonarr integration

Phase 4

- Overseerr integration

---

# Environment Variables

Discord

DISCORD_TOKEN
DISCORD_CHANNEL_ID
DISCORD_ADMIN_CHANNEL_ID

Radarr

RADARR_URL
RADARR_API_KEY

Sonarr

SONARR_URL
SONARR_API_KEY

Overseerr

OVERSEERR_URL
OVERSEERR_API_KEY

User Mapping

MIKE_ID
DEREK_ID
JAY_ID

OVERSEERR_MIKE
OVERSEERR_DEREK
OVERSEERR_JAY

---

# Current Status

Media Butler successfully:

- Runs locally.
- Runs in Docker.
- Sends Discord notifications.
- Supports Discord commands.
- Searches the Radarr library.