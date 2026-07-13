from services.media_service import MediaService
from views.search_results_view import SearchResultsView
from views.media_selection_view import MediaSelectionView


class FindCommand:
    """
    Searches the media library.
    """

    COMMAND = "find"
    DESCRIPTION = "Searches Radarr and Sonarr for matching media."

    def __init__(self):
        self.media = MediaService()

    async def execute(self, message):
        parts = message.content.split(maxsplit=1)

        if len(parts) < 2:
            await message.channel.send(
                "Usage: `!find <title>`"
            )
            return

        query = parts[1].strip()

        results = self.media.search(query)

        if not results:
            await message.channel.send(
                f'No media found matching "{query}".'
            )
            return

        embed = SearchResultsView.build(query, results)

        await message.channel.send(
            embed=embed,
            view=MediaSelectionView(
                results=results,
                requesting_user_id=message.author.id,
            ),
        )