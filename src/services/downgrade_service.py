"""Read-only discovery of smaller Arr manual-search releases."""

from collections import Counter
import re
from typing import Any

from models.downgrade import ReplacementCandidate
from models.media_analysis import MediaAnalysis
from services.analyze_service import languages, quality, size, text
from services.log_service import logger
from services.radarr_service import RadarrService
from services.sonarr_service import SonarrService

_BAD_RELEASE_WORDS = (
    "cam",
    "telesync",
    "tele sync",
    "telecine",
    "workprint",
    "hdts",
    " ts ",
    " tc ",
)

# These are expected when deliberately replacing an existing file with a
# smaller or lower-ranked release. They do not make the release unusable.
_ALLOWED_DOWNGRADE_REJECTION_PHRASES = (
    "existing file meets cutoff",
    "existing file is of equal or higher quality",
    "existing file is higher quality",
    "existing file has a higher quality",
    "quality for existing file is of equal or higher preference",
    "not an upgrade for existing file",
    "not an upgrade",
)


def _resolution_height(value: Any) -> int | None:
    """Normalize a numeric or text resolution into its vertical height."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    value_text = str(value)
    digits = "".join(character for character in value_text if character.isdigit())

    return int(digits) if digits else None


def _resolution_label(value: Any) -> str | None:
    """Return a normalized display label such as 1080p or 2160p."""
    height = _resolution_height(value)

    if height is None:
        return None

    return f"{height}p"


def _extract_quality_data(release: dict[str, Any]) -> dict[str, Any]:
    quality_wrapper = release.get("quality")

    if not isinstance(quality_wrapper, dict):
        return {}

    nested_quality = quality_wrapper.get("quality")

    if not isinstance(nested_quality, dict):
        return {}

    return nested_quality


def _extract_languages(release: dict[str, Any]) -> list[str]:
    """Normalize Arr language objects and strings into unique names."""
    raw_languages = release.get("languages") or release.get("language") or []

    return languages(raw_languages)


def _video_codec(release: dict[str, Any], release_name: str | None) -> str:
    """Return a supported codec, inferring it from a release title when needed."""
    raw_codec = text(release.get("videoCodec")) or text(release.get("videoFormat"))
    source = raw_codec or release_name or ""

    if re.search(r"(?<![a-z0-9])(?:hevc|h[ .]?265|x265)(?![a-z0-9])", source, re.I):
        return "HEVC"

    if re.search(r"(?<![a-z0-9])(?:avc|h[ .]?264|x264)(?![a-z0-9])", source, re.I):
        return "AVC"

    if re.search(r"(?<![a-z0-9])av1(?![a-z0-9])", source, re.I):
        return "AV1"

    return "Unknown"


def _extract_rejections(release: dict[str, Any]) -> list[str]:
    raw_rejections = release.get("rejections") or release.get("rejectionReasons") or []

    if not isinstance(raw_rejections, list):
        raw_rejections = [raw_rejections]

    return [
        rejection
        for rejection in (text(raw_rejection) for raw_rejection in raw_rejections)
        if rejection
    ]


def _blocking_rejections(release: dict[str, Any]) -> list[str]:
    """Return only rejection reasons that are not expected for a downgrade."""
    blocking: list[str] = []

    for rejection in _extract_rejections(release):
        normalized = rejection.casefold()

        if any(
            allowed_phrase in normalized
            for allowed_phrase in _ALLOWED_DOWNGRADE_REJECTION_PHRASES
        ):
            continue

        blocking.append(rejection)

    return blocking


class DowngradeService:
    """Uses Arr manual-search endpoints only; it never changes Arr state."""

    def __init__(self, radarr=None, sonarr=None):
        self.radarr = radarr or RadarrService()
        self.sonarr = sonarr or SonarrService()

    def candidates(
        self,
        media,
        analysis: MediaAnalysis,
    ) -> list[ReplacementCandidate]:
        current_size = analysis.total_size_bytes

        if current_size is None:
            return []

        releases = (
            self.sonarr.manual_search(media.id)
            if media.media_type == "series"
            else self.radarr.manual_search(media.id)
        )

        minimum_resolution = 720 if media.media_type == "series" else 1080

        candidates: list[ReplacementCandidate] = []
        rejection_counts: Counter[str] = Counter()

        for release in releases:
            if not isinstance(release, dict):
                rejection_counts["invalid release payload"] += 1
                continue

            candidate, rejection_reason = self._normalize_with_reason(
                release=release,
                title=media.title,
                current_size=current_size,
                minimum=minimum_resolution,
            )

            if candidate is None:
                rejection_counts[rejection_reason or "unknown"] += 1
                continue

            candidates.append(candidate)

        candidates = sorted(
            candidates,
            key=lambda candidate: candidate.size_bytes,
            reverse=True,
        )[:5]

        logger.info(
            "Downgrade discovery for %s: %s releases searched, "
            "%s acceptable candidates, rejection summary=%s",
            media.title,
            len(releases),
            len(candidates),
            dict(rejection_counts),
        )

        return candidates

    @staticmethod
    def _normalize(
        release: dict[str, Any],
        title: str,
        current_size: int,
        minimum: int,
    ) -> ReplacementCandidate | None:
        candidate, _ = DowngradeService._normalize_with_reason(
            release=release,
            title=title,
            current_size=current_size,
            minimum=minimum,
        )

        return candidate

    @staticmethod
    def _normalize_with_reason(
        release: dict[str, Any],
        title: str,
        current_size: int,
        minimum: int,
    ) -> tuple[ReplacementCandidate | None, str | None]:
        candidate_size = size(release)

        if candidate_size is None:
            return None, "unknown size"

        if candidate_size >= current_size:
            return None, "not smaller"

        release_name = text(release.get("releaseTitle")) or text(release.get("title"))

        bad_name = (release_name or "").casefold()

        if any(bad_word in f" {bad_name} " for bad_word in _BAD_RELEASE_WORDS):
            return None, "unusable release type"

        quality_data = _extract_quality_data(release)

        raw_resolution = release.get("resolution") or quality_data.get("resolution")

        resolution_height = _resolution_height(raw_resolution)

        if resolution_height is None:
            return None, "unknown resolution"

        if resolution_height < minimum:
            return None, "below minimum resolution"

        candidate_languages = _extract_languages(release)

        if not any(
            language.casefold() == "english" for language in candidate_languages
        ):
            return None, "English not present"

        blocking_rejections = _blocking_rejections(release)

        if blocking_rejections:
            return None, f"Arr rejection: {blocking_rejections[0]}"

        raw_quality = quality(release)

        if not raw_quality:
            raw_quality = text(quality_data.get("name"))

        score = release.get("customFormatScore")

        score = (
            score if isinstance(score, int) and not isinstance(score, bool) else None
        )

        savings = current_size - candidate_size

        return (
            ReplacementCandidate(
                title=title,
                size_bytes=candidate_size,
                quality=raw_quality,
                resolution=_resolution_label(raw_resolution),
                video_codec=_video_codec(release, release_name),
                languages=candidate_languages,
                indexer=text(release.get("indexer")),
                protocol=text(release.get("protocol")),
                custom_format_score=score,
                savings_bytes=savings,
                savings_percent=round(savings / current_size * 100),
                release_name=release_name,
            ),
            None,
        )
