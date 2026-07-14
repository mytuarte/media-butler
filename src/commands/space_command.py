from services.space_service import SpaceService
from views.largest_movies_view import LargestMoviesView
from views.space_view import SpaceView


class SpaceCommand:
    """
    Displays storage statistics for the media library.
    """

    COMMAND = "space"
    DESCRIPTION = "Displays media storage usage."

    def __init__(self):
        self.space = SpaceService()

    async def execute(self, message):
        result = self.space.get_summary()

        await message.channel.send(
            embed=SpaceView.build(result),
        )

        await message.channel.send(
            embed=LargestMoviesView.build(result),
        )