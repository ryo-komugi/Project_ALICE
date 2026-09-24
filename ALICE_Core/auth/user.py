from dataclasses import dataclass

from auth.user_status import UserStatus


@dataclass
class User:
    user_id: str
    display_name: str
    status: UserStatus