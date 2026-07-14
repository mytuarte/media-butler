from datetime import datetime, timedelta


class DeleteConfirmationService:
    def __init__(self):
        self.pending = {}

    def start_confirmation(
        self,
        user_id: int,
        media_result,
    ):
        self.pending[user_id] = {
            "media": media_result,
            "expires": datetime.now() + timedelta(seconds=60),
        }

    def get_confirmation(self, user_id: int):
        confirmation = self.pending.get(user_id)

        if confirmation is None:
            return None

        if datetime.now() > confirmation["expires"]:
            self.clear_confirmation(user_id)
            return None

        return confirmation

    def confirm(self, user_id: int):
        confirmation = self.get_confirmation(user_id)

        if confirmation is None:
            return None

        self.clear_confirmation(user_id)

        return confirmation["media"]

    def clear_confirmation(self, user_id: int):
        self.pending.pop(user_id, None)