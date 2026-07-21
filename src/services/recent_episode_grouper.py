from models.recent_download import RecentDownload


class RecentEpisodeGrouper:
    @staticmethod
    def group(
        downloads: list[RecentDownload],
    ) -> list[RecentDownload]:
        grouped: dict[
            tuple[str, str | None],
            RecentDownload,
        ] = {}

        for download in downloads:
            key = (
                download.title,
                download.requester,
            )

            if key not in grouped:
                grouped[key] = download
                continue

            existing = grouped[key]

            existing.size_bytes += download.size_bytes

            if existing.quality != download.quality and existing.quality != "Mixed":
                existing.quality = "Mixed"

            if download.downloaded_date > existing.downloaded_date:
                existing.downloaded_date = download.downloaded_date

            episode_lookup = {
                (season, episode): (
                    season,
                    episode,
                    title,
                )
                for season, episode, title in existing.episodes
            }

            for season, episode, title in download.episodes:
                episode_lookup[(season, episode)] = (
                    season,
                    episode,
                    title,
                )

            existing.episodes = sorted(
                episode_lookup.values(),
                key=lambda item: (
                    item[0],
                    item[1],
                ),
            )

        return list(grouped.values())
