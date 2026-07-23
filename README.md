# 🎬 Media Butler

Media Butler is a Discord bot that integrates with Plex, Overseerr, Radarr, and Sonarr to notify users when their requested media has finished downloading.

Instead of silently adding media to your Plex library, Media Butler automatically sends rich Discord notifications and mentions the user who requested the content.

---

## Features

### Movies
- ✅ Radarr webhook integration
- ✅ Download complete notifications
- ✅ Automatic Discord user mentions
- ✅ Overseerr requester lookup
- ✅ Docker deployment

### TV Shows
- ✅ Sonarr webhook integration
- ✅ Episode download notifications
- ✅ Automatic Discord user mentions
- ✅ Overseerr requester lookup

---

## Example Notifications

### Movie

```
🎬 The Lion King (1994)

Download Complete

👤 Requested By
@Mike

🎞 Quality
Bluray-1080p
```

---

### TV Episode

```
📺 The Office (US)

S01E03 • Health Care

Download Complete

👤 Requested By
@Mike

🎞 Quality
Bluray-1080p
```

---

# How It Works

```
                 Plex Watchlist
                       │
                       ▼
                  Overseerr
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
      Radarr                     Sonarr
         │                           │
         ▼                           ▼
      SABnzbd / Download Client
                 │
                 ▼
            Media Butler
                 │
                 ▼
              Discord
```

Media Butler listens for webhook events from Radarr and Sonarr.

When a download finishes, it:

1. Receives the webhook.
2. Looks up the requester through the Overseerr API.
3. Matches the requester to a Discord user.
4. Sends a Discord embed.
5. Mentions the requester.

## Media Attention

Media Attention monitors requested movies with `MEDIA_ATTENTION_STALL_MINUTES` and
requested TV **series** with `MEDIA_ATTENTION_TV_STALL_MINUTES` (120 minutes by
default). TV tracking is one item per series, never one alert per episode. It
ignores Season 0 specials and future/no-date episodes, considering only normal
episodes whose usable Sonarr air date/time is already due (date-only and naive
Sonarr values are interpreted as UTC). A newly aired missing weekly episode
starts a fresh series progress window. Large series continue to reset their
timer as episodes import or Sonarr queue bytes/percentage progress, so a long
active download does not itself alert.
Sonarr completion notifications are unchanged.

## Butler Health monitoring

Butler Health monitors infrastructure and service availability for Radarr, Sonarr,
SABnzbd (including queue access), Plex, Overseerr, qBittorrent, and configured
storage. qBittorrent monitoring only checks WebUI availability and authenticated
API access; it does not inspect torrents, download titles, queues, or pipeline
states. Individual media acquisition progress and stalls remain owned by Media
Attention.

qBittorrent monitoring is optional. Set all three values below to enable it; if
all are blank it is disabled. Supplying only some values is a configuration error.

```env
QBITTORRENT_URL=
QBITTORRENT_USERNAME=
QBITTORRENT_PASSWORD=
```

---

# Tech Stack

- Python 3.13
- Flask
- discord.py
- Docker
- GitHub
- Radarr API
- Sonarr API
- Overseerr API

---

# Project Structure

```
media-butler/
│
├── config/
├── data/
├── docker/
├── docs/
├── logs/
├── src/
│   ├── models/
│   ├── services/
│   └── main.py
│
├── docker.compose.yaml
├── requirements.txt
└── README.md
```

---

# Installation

Clone the repository

```bash
git clone https://github.com/mytuarte/media-butler.git
cd media-butler
```

Create a configuration file:

```
config/.env
```

Example:

```env
DISCORD_TOKEN=YOUR_DISCORD_TOKEN
DISCORD_CHANNEL_ID=YOUR_CHANNEL_ID

OVERSEERR_URL=http://your-overseerr:5055
OVERSEERR_API_KEY=YOUR_API_KEY

OVERSEERR_MIKE=michaelytuarte
MIKE_ID=123456789012345678
```

Build the Docker container

```bash
docker compose up -d --build
```

Configure Radarr and Sonarr webhooks to point to:

```
http://<media-butler-ip>:5000/radarr
```

and

```
http://<media-butler-ip>:5000/sonarr
```

---

# Current Status

## ✅ Implemented

- Movie notifications
- TV episode notifications
- Discord mentions
- Docker deployment
- Radarr integration
- Sonarr integration
- Overseerr integration

---

# Planned Features

- Discord slash commands
- Delete movies/shows directly from Discord
- List movies in library
- List TV shows in library
- Download statistics
- Movie posters in embeds
- TV posters in embeds
- Season-complete notifications
- Series-complete notifications
- Plex activity notifications
- Request queue management

---

# Roadmap

## v0.1

- ✅ Discord Bot
- ✅ Radarr Integration
- ✅ Overseerr Lookup

## v0.2

- ✅ Sonarr Integration
- ✅ TV Episode Notifications

## v0.3

- ⬜ Discord Slash Commands
- ⬜ Delete Media
- ⬜ Library Search

## v0.4

- ⬜ Posters
- ⬜ Better Embeds
- ⬜ Season Summary Notifications

---

# Contributing

Pull requests are welcome.

If you'd like to contribute, please open an issue first to discuss the proposed changes.

---

# License

MIT License

---

# Author

Michael Ytuarte

GitHub:
https://github.com/mytuarte

---

Media Butler is a personal project built to simplify media automation and notifications for Plex-based home servers.
