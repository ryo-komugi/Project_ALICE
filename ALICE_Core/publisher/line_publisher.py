import logging
import shutil
import config
from urllib.parse import quote
from pathlib import Path
from line.message_sender import MessageSender
from line.flex.download import DownloadFlex


logger = logging.getLogger(__name__)


class LinePublisher:
    MODULE_TITLES: dict[str, str] = {
        "transcript": "文字起こしが完了しました",
        "summary": "要約が完了しました",
        "minutes": "議事録作成が完了しました",
    }

    def __init__(self):
        self.sender = MessageSender()
        self.download_flex = DownloadFlex()

    def publish(self, filepath, user_id, module_name: str = "transcript", extra_files: dict[str, str] | None = None) -> None:
        filename = Path(filepath).name
        dst = Path(config.DIR_SHARE) / filename
        logger.info(f"[LinePublisher] Copy : {filepath} -> {dst} (module={module_name})")

        try:
            shutil.copy2(filepath, dst)
            download_url = f"{config.PUBLIC_URL}/download/{quote(filename)}"
            view_url = f"{config.PUBLIC_URL}/view/{quote(filename)}"
            title = self.MODULE_TITLES.get(module_name, "処理が完了しました")

            # extra_files の処理 (summary, commentary 等)
            items = [
                {
                    "title": title,
                    "filename": filename,
                    "download_url": download_url,
                    "view_url": view_url,
                }
            ]

            # 1. Summary item
            sum_filepath = (extra_files or {}).get("summary")
            if sum_filepath and Path(sum_filepath).exists():
                sum_filename = Path(sum_filepath).name
                sum_dst = Path(config.DIR_SHARE) / sum_filename
                shutil.copy2(sum_filepath, sum_dst)
                sum_download_url = f"{config.PUBLIC_URL}/download/{quote(sum_filename)}"
                sum_view_url = f"{config.PUBLIC_URL}/view/{quote(sum_filename)}"
                items.append({
                    "title": "要約レポート",
                    "filename": sum_filename,
                    "download_url": sum_download_url,
                    "view_url": sum_view_url,
                })
                logger.info(f"[LinePublisher] Copy summary: {sum_filepath} -> {sum_dst}")

            # 2. Commentary item
            comm_filepath = (extra_files or {}).get("commentary")
            if comm_filepath and Path(comm_filepath).exists():
                comm_filename = Path(comm_filepath).name
                comm_dst = Path(config.DIR_SHARE) / comm_filename
                shutil.copy2(comm_filepath, comm_dst)
                comm_download_url = f"{config.PUBLIC_URL}/download/{quote(comm_filename)}"
                comm_view_url = f"{config.PUBLIC_URL}/view/{quote(comm_filename)}"
                items.append({
                    "title": "解説・講評レポート",
                    "filename": comm_filename,
                    "download_url": comm_download_url,
                    "view_url": comm_view_url,
                })
                logger.info(f"[LinePublisher] Copy commentary: {comm_filepath} -> {comm_dst}")

            # 成果物通知: 長文テキストのベタ打ちは行わず、Webプレビューおよびダウンロードリンク付きFlexカードのみを送信 (パターンA)
            if len(items) > 1:
                alt_text = "議事録・要約レポートが届きました" if module_name == "minutes" else "要約および解説・講評レポートが届きました"
                flex = self.download_flex.create_carousel(items, alt_text=alt_text)
            else:
                flex = self.download_flex.create(
                    title=title,
                    filename=filename,
                    download_url=download_url,
                    view_url=view_url
                )
            self.sender.push_flex(user_id, flex)
        except Exception:
            logger.exception("[LinePublisher] Copy failed")
            raise

        logger.info("[LinePublisher] Copy complete")
