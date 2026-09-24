import sys
import json
from pathlib import Path
import requests

CORE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

import config

BASE_DIR = Path(__file__).parent


class RichMenuUploader:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {config.CHANNEL_ACCESS_TOKEN}"
        }

    def create_richmenu(self, json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            body = json.load(f)

        response = requests.post(
            f"{config.BASE_URL}/richmenu",
            headers={
                **self.headers,
                "Content-Type": "application/json"
            },
            json=body
        )

        response.raise_for_status()
        richmenu_id = response.json()["richMenuId"]
        print(f"Created : {richmenu_id}")
        return richmenu_id
    

    def upload_image(self, richmenu_id, image_path):
        with open(image_path, "rb") as f:
            response = requests.post(
                f"{config.BASE_DATA_URL}/richmenu/{richmenu_id}/content",
                headers={
                    **self.headers,
                    "Content-Type": "image/png"
                },
                data=f
            )
        response.raise_for_status()
        print("Image Uploaded")


    def set_default(self, richmenu_id):
        response = requests.post(
            f"{config.BASE_URL}/user/all/richmenu/{richmenu_id}", headers=self.headers)
        response.raise_for_status()
        print("Default Menu Set")


    def register(self, json_file, image_file, default=False):
        menu_name = Path(json_file).stem
        self.delete_by_name(menu_name)

        richmenu_id = self.create_richmenu(json_file)
        self.upload_image(richmenu_id, image_file)

        if default:
            self.set_default(richmenu_id)

        self.save_id(menu_name, richmenu_id)
        print(f"Registered : {menu_name} -> {richmenu_id}")
        return richmenu_id


    def list(self):
        response = requests.get(f"{config.BASE_URL}/richmenu/list", headers=self.headers)
        response.raise_for_status()
        return response.json()["richmenus"]


    def delete(self, richmenu_id):
        response = requests.delete(f"{config.BASE_URL}/richmenu/{richmenu_id}", headers=self.headers)
        response.raise_for_status() 
        print(f"Deleted : {richmenu_id}")


    def delete_by_name(self, name):
        menus = self.list()
        count = 0
        for menu in menus:
            if menu["name"] == name:
                self.delete(menu["richMenuId"])
                count += 1
        print(f"Deleted {count} menu(s): {name}")


    def save_id(self, menu_name, richmenu_id):
        ids_file = BASE_DIR / "richmenu_ids.json"
        if ids_file.exists():
            with open(ids_file, "r", encoding="utf-8") as f:
                ids = json.load(f)
        else:
            ids = {}

        ids[menu_name] = richmenu_id
        with open(ids_file, "w", encoding="utf=8") as f:
            json.dump(ids, f, indent=4, ensure_ascii=False)



if __name__ == "__main__":
    uploader = RichMenuUploader()
    uploader.register(BASE_DIR / "UserMenu.json", BASE_DIR / "UserMenu.png", default=True)
    uploader.register(BASE_DIR / "UploadMenu.json", BASE_DIR / "UploadMenu.png")