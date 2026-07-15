from models.command_channel import CommandChannel
from services.media_service import MediaService
from services.registry import services
from views.media_selection_view import MediaSelectionView
from views.search_results_view import SearchResultsView


class FindCommand:
    """
    Searches for movies and TV series.
    """

    COMMAND = "find"
    DESCRIPTION = "Searches your media library."

    CHANNELS = {
        CommandChannel.ADMIN,
        CommandChannel.MEDIA_SEARCH,
    }

    def __init__(self):
        self.media = MediaService()

    async def execute(self, message):
        parts = message.content.split(maxsplit=1)

        if len(parts) < 2:
            await message.channel.send("Usage: `!find <title>`")
            return

        query = parts[1].strip()

        results = self.media.search(query)

        if not results:
            response = await message.channel.send(f'No media found matching "{query}".')

            await services.search_channel.cleanup(
                channel=CommandChannel.MEDIA_SEARCH,
                user_message=message,
                bot_message=response,
            )

            return

        embed = SearchResultsView.build(
            query,
            results,
        )

        response = await message.channel.send(
            embed=embed,
            view=MediaSelectionView(
                results=results,
                requesting_user_id=message.author.id,
                mode="find",
            ),
        )

        await services.search_channel.cleanup(
            channel=CommandChannel.MEDIA_SEARCH,
            user_message=message,
            bot_message=response,
        )
