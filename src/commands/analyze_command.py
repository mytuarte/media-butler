from models.command_channel import CommandChannel
from services.media_service import MediaService
from views.media_selection_view import MediaSelectionView
from views.search_results_view import SearchResultsView
class AnalyzeCommand:
    COMMAND="analyze"
    DESCRIPTION="Displays technical and storage analysis for media."
    CHANNELS={CommandChannel.ADMIN}
    def __init__(self): self.media=MediaService()
    async def execute(self,message):
        parts=message.content.split(maxsplit=1)
        if len(parts)<2 or not parts[1].strip():
            await message.channel.send("Usage: `!analyze <title>`"); return
        query=parts[1].strip(); results=self.media.search(query)
        if not results:
            await message.channel.send(f'No media found matching "{query}".'); return
        await message.channel.send(embed=SearchResultsView.build(query,results),view=MediaSelectionView(results,message.author.id,mode="analyze"))
