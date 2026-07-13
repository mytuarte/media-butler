from services.scenario_service import ScenarioService
from views.movie_details_view import MovieDetailsView


class ScenarioCommand:
    """
    Developer command for rendering test scenarios.
    """

    COMMAND = "scenario"
    DESCRIPTION = "Displays developer test scenarios."

    def __init__(self):
        self.scenarios = ScenarioService()

    async def execute(self, message):
        parts = message.content.split(maxsplit=1)

        if len(parts) < 2:
            await message.channel.send(
                "Usage: `!scenario released`"
            )
            return

        scenario = parts[1].strip().lower()

        if scenario != "released":
            await message.channel.send(
                f'Unknown scenario: "{scenario}"'
            )
            return

        result = self.scenarios.released_not_downloaded()

        embed = MovieDetailsView.build(result)

        await message.channel.send(embed=embed)