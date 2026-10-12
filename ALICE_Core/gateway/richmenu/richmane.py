import json
import logging
from pathlib import Path
import threading
import requests
import config

logger = logging.getLogger(__name__)


class RichMenu:
    def __init__(self):
        self.headers = {"Authorization": f"Bearer {config.CHANNEL_ACCESS_TOKEN}"}

    def _do_switch(self, user_id, menu_name):
        try:
            menu_ids = self.laod_menu_ids()
            richmenu_id = menu_ids.get(menu_name)
            if not richmenu_id:
                logger.error(f"[RichMenu] Menu not found: {menu_name}")
                return
            response = requests.post(
                f"{config.BASE_URL}/user/{user_id}/richmenu/{richmenu_id}",
                headers=self.headers,
                timeout=5
            )
            response.raise_for_status()
            logger.info(f"[RichMenu] Changed for {user_id}: {menu_name}")
        except Exception as e:
            logger.warning(f"[RichMenu] switch failed for {user_id} -> {menu_name}: {e}")

    def switch(self, user_id, menu_name, async_req=True):
        if async_req:
            t = threading.Thread(target=self._do_switch, args=(user_id, menu_name), daemon=True)
            t.start()
        else:
            self._do_switch(user_id, menu_name)

    def _do_unlink(self, user_id):
        try:
            response = requests.delete(
                f"{config.BASE_URL}/user/{user_id}/richmenu",
                headers=self.headers,
                timeout=5
            )
            response.raise_for_status()
            logger.info(f"[RichMenu] Unlinked richmenu for {user_id}")
        except Exception as e:
            logger.warning(f"[RichMenu] unlink failed for {user_id}: {e}")

    def unlink(self, user_id, async_req=True):
        if async_req:
            t = threading.Thread(target=self._do_unlink, args=(user_id,), daemon=True)
            t.start()
        else:
            self._do_unlink(user_id)

    def laod_menu_ids(self):
        ids_file = (Path(__file__).parent / "richmenu_ids.json")
        with open(ids_file, "r", encoding="utf-8") as f:
            return json.load(f)
