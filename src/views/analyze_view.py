"""Safe, compact Discord presentation for normalized analysis models."""
import discord
from models.media_analysis import MovieAnalysis, SeriesAnalysis
from services.analyze_service import distinct_release, safe_relative_path

TITLE_LIMIT, DESCRIPTION_LIMIT, FIELD_NAME_LIMIT, FIELD_VALUE_LIMIT, EMBED_LIMIT = 256, 4096, 256, 1024, 6000
OMITTED = "Additional analysis details omitted."

def format_bytes(value: int | float | None) -> str:
    if value is None or value < 0: return "Unavailable"
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB": return f"{amount:.2f}".rstrip("0").rstrip(".") + f" {unit}"
        amount /= 1024

def limited_lines(lines: list[str], limit: int = FIELD_VALUE_LIMIT) -> str:
    """Keep complete lines within a hard limit, adding omission only if it fits."""
    if limit <= 0:
        return ""
    marker = OMITTED if len(OMITTED) <= limit else "…" if limit else ""
    kept: list[str] = []
    used = 0
    for line in lines:
        separator = 1 if kept else 0
        if used + separator + len(line) <= limit:
            kept.append(line)
            used += separator + len(line)
            continue
        marker_separator = 1 if kept else 0
        if used + marker_separator + len(marker) <= limit:
            kept.append(marker)
        elif not kept and marker:
            kept.append(marker[:limit])
        return "\n".join(kept)
    return "\n".join(kept) or "Unavailable"[:limit]

def _clip(value, limit): return value if len(value) <= limit else value[:max(0, limit-len(OMITTED)-1)] + "…"
def _dist(values): return [f"{name} × {count}" for name,count in values.items()]

class AnalyzeView:
    """Build embeds while enforcing Discord's content limits."""
    @staticmethod
    def build(analysis):
        embed=discord.Embed(title="🔎 Media Analysis", color=discord.Color.blurple())
        icon="📺" if analysis.media_type=="series" else "🎬"; year=f" ({analysis.year})" if analysis.year else ""
        embed.description=_clip(f"{icon} **{analysis.title}{year}**", DESCRIPTION_LIMIT)
        if isinstance(analysis,MovieAnalysis): AnalyzeView._movie(embed,analysis)
        else: AnalyzeView._series(embed,analysis)
        return AnalyzeView._enforce(embed)
    @staticmethod
    def _add(embed,name,lines,inline=False):
        if len(embed.fields)<25: embed.add_field(name=_clip(name,FIELD_NAME_LIMIT),value=limited_lines(lines),inline=inline)
    @staticmethod
    def _movie(embed,a):
        AnalyzeView._add(embed,"File",[f"Size: {format_bytes(a.size_bytes)}"]+([f"Runtime: {int(a.runtime_minutes)//60}h {int(a.runtime_minutes)%60}m"] if a.runtime_minutes is not None else [])+([f"Storage Rate: {format_bytes(a.size_per_hour_bytes)}/hour"] if a.size_per_hour_bytes is not None else [])+([f"Estimated Bitrate: {a.estimated_total_bitrate_mbps:.1f} Mbps"] if a.estimated_total_bitrate_mbps is not None else []))
        video=[f"{k}: {v}" for k,v in (("Quality",a.quality),("Resolution",a.resolution),("Codec",a.video_codec),("Dynamic Range",a.video_dynamic_range)) if v]
        audio=[f"{k}: {v}" for k,v in (("Codec",a.audio_codec),("Channels",a.audio_channels),("Languages",", ".join(a.audio_languages) if a.audio_languages else None)) if v]
        filename = safe_relative_path(a.file_relative_path)
        release = distinct_release(filename, a.original_release_name)
        source=[f"{k}: {v}" for k,v in (("Filename",filename),("Release",release)) if v]
        if video: AnalyzeView._add(embed,"Video",video,True)
        if audio: AnalyzeView._add(embed,"Audio",audio,True)
        if source: AnalyzeView._add(embed,"Source",source)
        if a.warnings: AnalyzeView._add(embed,"Availability",a.warnings)
    @staticmethod
    def _series(embed,a:SeriesAnalysis):
        AnalyzeView._add(embed,"Storage",[f"Total Size: {format_bytes(a.total_size_bytes)}",f"Episode Files: {a.total_episode_files}",f"Average File Size: {format_bytes(a.average_episode_size_bytes)}",f"Released Episodes: {a.downloaded_released_episode_count} / {a.released_episode_count} downloaded"])
        tech=[]
        for name,values in (("Quality",a.quality_distribution),("Resolution",a.resolution_distribution),("Video Codec",a.video_codec_distribution),("Audio Codec",a.audio_codec_distribution)):
            if values: tech += [f"**{name}:**",*_dist(values)]
        if tech: AnalyzeView._add(embed,"Technical Distribution",tech)
        seasons=sorted(a.seasons,key=lambda s:(s.total_size_bytes is None, -(s.total_size_bytes or 0), s.season_number))
        lines=[f"{'Specials' if s.season_number==0 else f'S{s.season_number:02d}'} — Total Size: {format_bytes(s.total_size_bytes)} — {s.file_count} files — avg {format_bytes(s.average_file_size_bytes)}" for s in seasons[:10]]
        if len(seasons)>10: lines.append(f"Showing 10 largest of {len(seasons)} seasons.")
        if lines: AnalyzeView._add(embed,"Largest Seasons",lines)
        if a.warnings: AnalyzeView._add(embed,"Availability",a.warnings)
        files=[]
        for e in a.largest_episode_files:
            label=f"S{e.season_number:02d}E{e.episode_number:02d}" if e.season_number is not None and e.episode_number is not None else "Unknown episode"
            files.append(f"{label}{' — '+e.title if e.title else ''} — {format_bytes(e.size_bytes)}{' — '+e.quality if e.quality else ''}")
        if files: AnalyzeView._add(embed,"Largest Episode Files",files)
    @staticmethod
    def _enforce(embed):
        embed.title=_clip(embed.title,TITLE_LIMIT); embed.description=_clip(embed.description or "",DESCRIPTION_LIMIT)
        used = len(embed.title) + len(embed.description)
        fields = [(field.name, field.value, field.inline) for field in embed.fields]
        embed.clear_fields()
        for name, value, inline in fields:
            remaining = EMBED_LIMIT - used - len(name)
            if remaining < 1:
                break
            safe_value = limited_lines(value.splitlines(), min(FIELD_VALUE_LIMIT, remaining))
            if not safe_value:
                break
            embed.add_field(name=name, value=safe_value, inline=inline)
            used += len(name) + len(safe_value)
        return embed
