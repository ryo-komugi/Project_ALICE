from dataclasses import dataclass
from linebot.v3.messaging import ApiClient, Configuration, MessagingApi
from config import CHANNEL_ACCESS_TOKEN


@dataclass
class Profile:
    display_name: str


class ProfileManager:
    def __init__(self):
        configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
        self.api_client = ApiClient(configuration)
        self.messaging_api = MessagingApi(self.api_client)

    def get_profile(self, user_id: str) -> Profile:
        response = self.messaging_api.get_profile(user_id)
        return Profile(
            display_name=response.display_name
        )
