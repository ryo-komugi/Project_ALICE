from enum import Enum


class UserStatus(str, Enum):
    WAIT_INVITE_CODE = "WAIT_INVITE_CODE"
    READY = "READY"
    REJECTED = "REJECTED"
