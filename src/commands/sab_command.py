import json

from services.sabnzbd_client import SabnzbdClient


class SabCommand:
    """
    Developer command for inspecting the SABnzbd queue.
    """

    COMMAND = "sab"
    DESCRIPTION = "Displays the current SABnzbd queue."

    def __init__(self):
        self.client = SabnzbdClient()

    async def execute(self, message):
        try:
            result = self.client.get_queue()

            formatted = json.dumps(
                result,
                indent=2,
            )

            # Discord code blocks are limited to 2000 characters
            if len(formatted) > 1800:
                formatted = formatted[:1800] + "\n..."

            await message.channel.send(
                f"```json\n{formatted}\n```"
            )

        except Exception as ex:
            await message.channel.send(
                f"❌ SABnzbd request failed.\n```{ex}```"
            )