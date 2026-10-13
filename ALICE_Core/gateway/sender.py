from linebot.v3.messaging import (ApiClient, Configuration, MessagingApi, ReplyMessageRequest, PushMessageRequest, TextMessage, FlexMessage, FlexContainer)
import config


class MessageSender:
    def __init__(self):
        configuration = Configuration(access_token=config.CHANNEL_ACCESS_TOKEN, host=config.BASE_URL.removesuffix("/v2/bot"))
        self.api_client = ApiClient(configuration)
        self.messaging_api = MessagingApi(self.api_client)

    def reply_text(self, reply_token: str, text: str) -> None:
        self.messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[
                    TextMessage(text=text)
                ]
            )
        )

    def push_text(self, user_id, text):
        self.messaging_api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=text)]
            )
        )

    def push_file(self, user_id, url):
        pass

    def push_flex(self, user_id, flex):
        self.messaging_api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[
                    FlexMessage(
                        alt_text=flex["altText"],
                        contents=FlexContainer.from_dict(flex["contents"])
                    )
                ]
            )
        )
