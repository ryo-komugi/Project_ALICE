import logging
import version


class Logger:
    """ALICE_Transcript 標準ロガー (標準出力へ出力し、CoreWorker 側で Workspace ログへ集約)"""

    def __init__(self):
        self.logger = logging.getLogger("ALICE_Transcript")
        self.logger.setLevel(logging.INFO)

        # 二重登録防止
        if not self.logger.handlers:
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            console = logging.StreamHandler()
            console.setFormatter(formatter)
            self.logger.addHandler(console)

            self.info("=" * 50)
            self.info(version.FULL_VERSION)
            self.info("=" * 50)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)