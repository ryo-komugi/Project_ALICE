import os
from linebot.v3.messaging import (ApiClient, Configuration, MessagingApiBlob)
import config


class ContentDownloader:
    def __init__(self):
        configuration = Configuration(
            access_token=config.CHANNEL_ACCESS_TOKEN,
            host=config.BASE_DATA_URL.removesuffix("/v2/bot"),
        )
        self.api_client = ApiClient(configuration)
        self.blob_api = MessagingApiBlob(self.api_client)

    def download(self, message_id: str, save_path: str) -> None:
        response = self.blob_api.get_message_content(message_id)
        with open(save_path, "wb") as f:
            f.write(response)
