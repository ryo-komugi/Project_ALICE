import hmac
import base64
import hashlib


class SignatureVerifier:
    def __init__(self, channel_secret: str):
        self.channel_secret = channel_secret.encode("utf-8")

    def verify(self, body: bytes, signature: str) -> bool:
        digest = hmac.new(
            self.channel_secret,
            body,
            hashlib.sha256,
        ).digest()

        expected_signature = base64.b64encode(digest).decode("utf-8")

        return hmac.compare_digest(expected_signature, signature)
