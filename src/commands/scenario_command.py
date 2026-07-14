from models.command_channel import CommandChannel
from services.scenario_service import ScenarioService
from views.movie_details_view import MovieDetailsView
from views.series_details_view import SeriesDetailsView


class ScenarioCommand:
    """
    Developer command for rendering test scenarios.
    """

    COMMAND = "scenario"
    DESCRIPTION = "Displays developer test scenarios."

    CHANNELS = {
        CommandChannel.ADMIN,
    }

    def __init__(self):
        self.scenarios = ScenarioService()

    async def execute(self, message):
        parts = message.content.split(maxsplit=1)

        if len(parts) < 2:
            await message.channel.send(
                "Usage: `!scenario <released|awaiting|downloading>`"
            )
            return

        scenario = parts[1].strip().lower()

        match scenario:
            case "released":
                result = self.scenarios.released_not_downloaded()
                embed = MovieDetailsView.build(result)

            case "awaiting":
                result = self.scenarios.awaiting_release()
                embed = MovieDetailsView.build(result)

            case "downloading":
                result = self.scenarios.downloading_series()
                embed = SeriesDetailsView.build(result)

            case _:
                await message.channel.send(
                    f'Unknown scenario: "{scenario}"'
                )
                return

        await message.channel.send(
            embed=embed,
        )