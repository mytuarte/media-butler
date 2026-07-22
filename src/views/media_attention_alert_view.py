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
    }

    @classmethod
    def build(cls, alert: MediaAttentionAlert, snapshot: PipelineSnapshot, stuck_minutes: int):
        embed = discord.Embed(title="⚠️ Media Attention", color=0xF1C40F)
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
