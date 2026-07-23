import discord

from models.media_attention import MediaAttentionAlert, PipelineSnapshot


class MediaAttentionAlertView:
    """Discord presentation only; monitoring decisions remain in the service."""

    STAGE_LABELS = {
        "waiting_for_arr": "Waiting for Radarr",
        "arr_searching": "Radarr searching",
        "downloading": "Downloading",
        "import_pending": "Import pending",
        "plex_sync_pending": "Plex sync pending",
        "waiting_for_sonarr": "Waiting for Sonarr",
        "sonarr_searching": "Sonarr searching",
        "series_caught_up": "Series caught up",
    }

    @classmethod
    def build(cls, alert: MediaAttentionAlert, snapshot: PipelineSnapshot, stuck_minutes: int):
        embed = discord.Embed(title="⚠️ Media Attention", color=0xF1C40F)
        if alert.media_type.value == "tv":
            return cls._build_tv(alert, snapshot, stuck_minutes)
        embed.add_field(name="🎬 Movie", value=alert.title, inline=False)
        embed.add_field(name="Status", value=cls.STAGE_LABELS[alert.stage.value], inline=True)
        embed.add_field(name="Stuck for", value=f"{stuck_minutes} minutes", inline=True)
        details = [
            f"Radarr: {'Movie found' if snapshot.arr_evidence.get('present') else 'No movie'}",
            f"SAB: {snapshot.sab_evidence.get('status') or ('Completed' if snapshot.sab_evidence.get('completed') else 'No activity')}",
            f"Plex: {'Available' if snapshot.plex_evidence.get('available') else 'Unavailable'}",
        ]
        if snapshot.sab_evidence.get("percent") is not None:
            details.insert(2, f"Progress: {snapshot.sab_evidence['percent']}%")
        embed.add_field(name="Details", value="\n".join(details), inline=False)
        return embed

    @classmethod
    def _build_tv(cls, alert, snapshot, stuck_minutes):
        embed = discord.Embed(title="⚠️ Media Attention", color=0xF1C40F)
        embed.add_field(name="📺 Series", value=alert.title, inline=False)
        embed.add_field(name="Status", value=cls.STAGE_LABELS[alert.stage.value], inline=True)
        embed.add_field(name="Stuck for", value=f"{stuck_minutes} minutes", inline=True)
        progress = snapshot.episode_progress
        episode_detail = (
            f"Released Episodes: {progress.released_count}\n"
            f"Downloaded Episodes: {progress.imported_released_count}\n"
            f"Missing Episodes: {len(progress.missing_episode_keys)}"
            if progress is not None
            else "Unavailable until the series reaches Sonarr."
        )
        embed.add_field(name="Episode Progress", value=episode_detail, inline=False)
        details = [f"Sonarr: {'Series found' if snapshot.arr_evidence.get('present') else 'No series'}"]
        if snapshot.sab_evidence.get("status"):
            details.append(f"Queue: {snapshot.sab_evidence['status']}")
        if snapshot.sab_evidence.get("percent") is not None:
            details.append(f"Progress: {snapshot.sab_evidence['percent']}%")
        embed.add_field(name="Details", value="\n".join(details), inline=False)
        return embed

    @classmethod
    def build_resolved(cls, alert: MediaAttentionAlert, snapshot: PipelineSnapshot):
        embed = discord.Embed(title="✅ Media Attention Resolved", color=0x2ECC71)
        embed.add_field(name="📺 Series" if alert.media_type.value == "tv" else "🎬 Movie", value=alert.title, inline=False)
        embed.add_field(name="Status", value="Progress resumed", inline=True)
        embed.add_field(name="Previous stage", value=alert.stage.name, inline=True)
        details = []
        if snapshot.sab_evidence.get("percent") is not None:
            details.append(f"{'Download' if alert.media_type.value == 'tv' else 'SAB'} progress: {snapshot.sab_evidence['percent']}%")
        else:
            details.append(snapshot.stage_detail)
        embed.add_field(name="Details", value="\n".join(details), inline=False)
        return embed
