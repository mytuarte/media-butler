"""Read-only discovery of smaller Arr manual-search releases."""
from typing import Any
from models.downgrade import ReplacementCandidate
from models.media_analysis import MediaAnalysis
from services.analyze_service import codec, languages, quality, resolution, size, text
from services.radarr_service import RadarrService
from services.sonarr_service import SonarrService

_BAD_RELEASE_WORDS = ("cam", "telesync", "tele sync", "telecine", "workprint", "hdts", " ts ", " tc ")


def _resolution_height(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(character for character in value if character.isdigit())
    return int(digits) if digits else None


class DowngradeService:
    """Uses Arr manual-search endpoints only; it never changes Arr state."""
    def __init__(self, radarr=None, sonarr=None):
        self.radarr = radarr or RadarrService()
        self.sonarr = sonarr or SonarrService()

    def candidates(self, media, analysis: MediaAnalysis) -> list[ReplacementCandidate]:
        current_size = analysis.total_size_bytes
        if current_size is None:
            return []
        releases = (self.sonarr.manual_search(media.id) if media.media_type == "series"
                    else self.radarr.manual_search(media.id))
        minimum = 720 if media.media_type == "series" else 1080
        candidates = [candidate for release in releases if isinstance(release, dict)
                      if (candidate := self._normalize(release, media.title, current_size, minimum))]
        return sorted(candidates, key=lambda candidate: candidate.size_bytes, reverse=True)[:5]

    @staticmethod
    def _normalize(release: dict[str, Any], title: str, current_size: int, minimum: int) -> ReplacementCandidate | None:
        candidate_size = size(release)
        release_name = text(release.get("releaseTitle")) or text(release.get("title"))
        quality_data = release.get("quality") if isinstance(release.get("quality"), dict) else {}
        nested_quality = quality_data.get("quality") if isinstance(quality_data.get("quality"), dict) else {}
        candidate_resolution = resolution(release.get("resolution") or nested_quality.get("resolution"))
        candidate_languages = languages(release.get("languages") or release.get("language"))
        rejection_reasons = release.get("rejections") or release.get("rejectionReasons") or []
        bad_name = (release_name or "").casefold()
        if (candidate_size is None or candidate_size >= current_size or
                _resolution_height(candidate_resolution) is None or _resolution_height(candidate_resolution) < minimum or
                "English" not in candidate_languages or rejection_reasons or
                any(word in f" {bad_name} " for word in _BAD_RELEASE_WORDS)):
            return None
        raw_quality = quality(release)
        raw_codec = release.get("videoCodec") or release.get("videoFormat")
        score = release.get("customFormatScore")
        score = score if isinstance(score, int) and not isinstance(score, bool) else None
        savings = current_size - candidate_size
        return ReplacementCandidate(
            title=title, size_bytes=candidate_size, quality=raw_quality,
            resolution=candidate_resolution, video_codec=codec(raw_codec),
            languages=candidate_languages, indexer=text(release.get("indexer")),
            protocol=text(release.get("protocol")), custom_format_score=score,
            savings_bytes=savings, savings_percent=round(savings / current_size * 100),
            release_name=release_name,
        )
