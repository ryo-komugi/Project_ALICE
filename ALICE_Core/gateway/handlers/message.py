import logging
import os
import config
from pathlib import Path
from auth.auth_manager import AuthManager
from repository.user_repository import UserRepository
from gateway.sender import MessageSender
from auth.user_status import UserStatus
from gateway.session import SessionManager
from gateway.downloader import ContentDownloader
from gateway.richmenu.richmane import RichMenu
from hub.container import job_service, job_queue, workspace_manager, core_worker
from core.system_settings import is_maintenance_active, get_maintenance_message, is_admin_bypass_allowed


logger = logging.getLogger(__name__)

# LINE Session Workflow名からCore Job Workflowリストへの変換マップ
WORKFLOW_MAP: dict[str, list[str]] = {
    "Transcript": ["transcript"],
    "Summary": ["transcript", "summary"],
    "Minutes": ["transcript", "summary", "minutes"],
}


class MessageHandler:
    def __init__(self):
        self.repository = UserRepository()
        self.auth = AuthManager()
        self.sender = MessageSender()
        self.session_manager = SessionManager()
        self.downloader = ContentDownloader()
        self.richmenu = RichMenu()

    def _on_burst_end(self, user_id: str):
        logger.info(f"[MessageHandler] Burst reception ended for user {user_id}. Switching richmenu to UserMenu.")
        self.richmenu.switch(user_id, "UserMenu")

    def get_queue_status_text(self, user_id: str | None = None) -> str:
        return job_service.get_queue_status_text(user_id=user_id)

    def handle(self, event: dict) -> None:
        logger.info("[MessageHandler] Event     : Message")
        user_id = event["source"]["userId"]
        reply_token = event["replyToken"]
        message_type = event["message"]["type"]
        logger.info(f"[MessageHandler] Type      : {message_type}")
        logger.info(f"[MessageHandler] User      : {user_id}")

        # --- メンテナンスモードガード ---
        if is_maintenance_active():
            is_admin = bool(config.LINE_ADMIN_USER and user_id == config.LINE_ADMIN_USER)
            if is_admin and is_admin_bypass_allowed():
                logger.info(f"[MessageHandler] Maintenance mode active, but admin user {user_id} bypassed.")
            else:
                logger.info(f"[MessageHandler] Maintenance mode active: returning maintenance message to {user_id}")
                self.sender.reply_text(reply_token, get_maintenance_message())
                return

        text = None
        if message_type == "text":
            text = event["message"]["text"]
            logger.info(f"[MessageHandler] Text      : {text}")

        user = self.repository.find(user_id)

        if user is None:
            self.sender.reply_text(reply_token, "ユーザー情報が見つかりません。\n一度友だち追加し直してください。")
            return

        if user.status == UserStatus.REJECTED:
            logger.info(f"[MessageHandler] Rejected user access: {user_id}")
            self.sender.reply_text(reply_token, "現在、このアカウントはご利用いただけません。")
            return

        if user.status == UserStatus.WAIT_INVITE_CODE:
            logger.info("[MessageHandler] Waiting invite code")

            if self.auth.verify_invite_code(user_id, text):
                logger.info("[MessageHandler] Invite code accepted")
                self.richmenu.switch(user_id, "UserMenu")
                self.sender.reply_text(reply_token, "認証が完了しました。\n\nようこそ。Project_ALICEへ。")
            else:
                logger.info("[MessageHandler] Invite code rejected")
                self.sender.reply_text(reply_token, "招待コードが違います。")
            return

        if user.status == UserStatus.READY:
            if message_type == "text":
                self.handle_text(user, user_id, reply_token, text)
                return
            if message_type == "audio":
                self.handle_audio(user, user_id, reply_token, event)
                return
            if message_type == "file":
                self.handle_file(user, user_id, reply_token, event)
                return
            self.sender.reply_text(reply_token, "現在このファイル形式には対応していません。")
            return

        logger.warning(
            f"[MessageHandler] Unknown status : {user.status}"
        )
        self.sender.reply_text(
            reply_token,
            "ユーザー状態が不正です。"
        )

    def handle_text(self, user, user_id, reply_token, text):
        session = self.session_manager.get(user_id)
        logger.info(f"[MessageHandler] Ready user (session state={session.state}, workflow={session.workflow})")

        # 共通コマンド・機能選択のハンドリング
        if text == "キャンセル":
            if session.state == "WAIT_FILE":
                self.session_manager.reset(user_id)
                logger.info(f"[Session] State     : IDLE")
                logger.info(f"[Session] User      : {user_id}")
                self.richmenu.switch(user_id, "UserMenu")
                self.sender.reply_text(reply_token, "受付をキャンセルしました。")
            else:
                self.sender.reply_text(reply_token, "現在処理中の受付はありません。")
            return

        if text == "送信方法":
            msg = (
                "【音声ファイルの送信方法】\n\n"
                "1. LINEのトーク画面左下の「＋」ボタンを押します。\n"
                "2. 「ファイル」を選択し、端末内の音声ファイル（MP3 / M4A / WAV）を選択して送信してください。\n"
                "※ LINEのボイスメッセージ録音機能でそのまま音声を送ることも可能です。"
            )
            self.sender.reply_text(reply_token, msg)
            return

        if text == "文字起こし":
            self.session_manager.set_wait_file(user_id, "Transcript")
            logger.info("[MessageHandler] Workflow  : Transcript")
            logger.info(f"[Session] State     : WAIT_FILE")
            logger.info(f"[Session] User      : {user_id}")
            self.richmenu.switch(user_id, "UploadMenu")
            self.sender.reply_text(reply_token, "文字起こしですね。\n\n音声ファイルを送信してください。")
            return

        if text in ["要約", "要約作成", "Summary"]:
            self.session_manager.set_wait_file(user_id, "Summary")
            logger.info("[MessageHandler] Workflow  : Summary")
            logger.info(f"[Session] State     : WAIT_FILE")
            logger.info(f"[Session] User      : {user_id}")
            self.richmenu.switch(user_id, "UploadMenu")
            self.sender.reply_text(reply_token, "要約ですね。\n\n音声ファイルを送信してください。")
            return

        if text in ["議事録", "議事録作成", "Minutes"]:
            self.session_manager.set_wait_file(user_id, "Minutes")
            logger.info("[MessageHandler] Workflow  : Minutes")
            logger.info(f"[Session] State     : WAIT_FILE")
            logger.info(f"[Session] User      : {user_id}")
            self.richmenu.switch(user_id, "UploadMenu")
            self.sender.reply_text(reply_token, "議事録ですね。\n\n音声ファイルを送信してください。")
            return

        if text in ["Queue", "queue", "キュー", "Queue確認"]:
            self.sender.reply_text(reply_token, self.get_queue_status_text(user_id))
            return

        if text == "ヘルプ":
            msg = (
                "【ALICE の使い方】\n\n"
                "リッチメニューから利用したい機能を選択し、音声ファイルを送信してください。\n\n"
                "■ 文字起こし:\n"
                "音声から話者を特定し、タイムスタンプ付きのテキスト（文字起こし）を作成します。\n\n"
                "■ 要約:\n"
                "文字起こしを行った上で、AIが重要な論点や決定事項を箇条書きで要約します。\n\n"
                "■ 議事録:\n"
                "会話から決定事項やTODO、議題経緯を抽出し、議事録を作成します。\n\n"
                "■ Queue:\n"
                "現在の処理待ち件数や待機状況を確認できます。\n\n"
                "※ 対応フォーマット: MP3 / M4A / WAV"
            )
            self.sender.reply_text(reply_token, msg)
            return

        # WAIT_FILE 中にその他のテキストが送信された場合
        if session.state == "WAIT_FILE":
            if session.last_file_at is not None:
                # 受付完了後のテキスト（「ありがとう」等）は受付終了として通常メニューに復帰
                self.session_manager.reset(user_id)
                self.richmenu.switch(user_id, "UserMenu")
                return
            self.sender.reply_text(reply_token, "音声ファイルを送信してください。\n中止する場合は「キャンセル」を選択してください。")
            return

        self.sender.reply_text(reply_token, "この機能にはまだ対応していません。\nリッチメニューから機能を選択してください。")

    def handle_file(self, user, user_id, reply_token, event):
        logger.info("[MessageHandler] File message")
        session = self.session_manager.get(user_id)

        if not self.session_manager.can_accept_file(user_id):
            self.session_manager.reset(user_id)
            self.richmenu.switch(user_id, "UserMenu")
            self.sender.reply_text(reply_token, "先にリッチメニューから機能を選択してください。")
            return

        message_id = event["message"]["id"]
        file_name = event["message"]["fileName"]
        workflow_type = session.workflow or "Transcript"
        job_workflow = WORKFLOW_MAP.get(workflow_type, ["transcript"])

        logger.info(f"[MessageHandler] Workflow  : {workflow_type} -> {job_workflow}")
        logger.info(f"[MessageHandler] File      : {file_name}")
        logger.info(f"[MessageHandler] MessageID : {message_id}")
        
        try:
            save_path = os.path.join(config.DIR_INBOX, file_name)
            self.downloader.download(message_id, str(save_path))
            logger.info(f"[MessageHandler] Downloaded : {save_path}")
            
            # --- Hub JobService 経由で Workspace 生成 & Queue 投入 ---
            job = job_service.submit_job(
                user_id=user_id,
                src_file=save_path,
                workflow=job_workflow,
                original_filename=file_name,
            )
            logger.info(f"[MessageHandler] Job submitted via JobService: {job.job_id}")

            # inbox の一時ファイル削除
            if os.path.exists(save_path):
                os.remove(save_path)

            self.session_manager.record_file_received(user_id, on_burst_end=self._on_burst_end)
            logger.info(f"[Session] Burst updated for User: {user_id}")
            
            if workflow_type == "Minutes":
                reply_prefix = "受付けました。要約・議事録の作成を開始します。"
            elif workflow_type == "Summary":
                reply_prefix = "受付けました。要約を開始します。"
            else:
                reply_prefix = "受付けました。文字起こしを開始します。"
            reply_msg = f"{reply_prefix}\n\n{self.get_queue_status_text(user_id)}"
            self.sender.reply_text(reply_token, reply_msg)
        
        except Exception as e:
            logger.exception(e)
            self.sender.reply_text(reply_token, "ファイル受付中にエラーが発生しました。")

    def handle_audio(self, user, user_id, reply_token, event):
        logger.info("[MessageHandler] Audio message")

        session = self.session_manager.get(user_id)

        if not self.session_manager.can_accept_file(user_id):
            self.session_manager.reset(user_id)
            self.richmenu.switch(user_id, "UserMenu")
            self.sender.reply_text(reply_token, "先にリッチメニューから機能を選択してください。")
            return

        message_id = event["message"]["id"]
        file_name = f"audio_{message_id}.m4a"
        workflow_type = session.workflow or "Transcript"
        job_workflow = WORKFLOW_MAP.get(workflow_type, ["transcript"])

        logger.info(f"[MessageHandler] Audio accepted : {workflow_type} -> {job_workflow}")
        logger.info(f"[MessageHandler] File      : {file_name}")
        logger.info(f"[MessageHandler] MessageID : {message_id}")

        try:
            save_path = os.path.join(config.DIR_INBOX, file_name)
            self.downloader.download(message_id, str(save_path))
            logger.info(f"[MessageHandler] Downloaded : {save_path}")

            # --- Hub JobService 経由で Workspace 生成 & Queue 投入 ---
            job = job_service.submit_job(
                user_id=user_id,
                src_file=save_path,
                workflow=job_workflow,
                original_filename=file_name,
            )
            logger.info(f"[MessageHandler] Job submitted via JobService: {job.job_id}")

            # inbox の一時ファイル削除
            if os.path.exists(save_path):
                os.remove(save_path)

            self.session_manager.record_file_received(user_id, on_burst_end=self._on_burst_end)
            logger.info(f"[Session] Burst updated for User: {user_id}")

            if workflow_type == "Minutes":
                reply_prefix = "受付けました。要約・議事録の作成を開始します。"
            elif workflow_type == "Summary":
                reply_prefix = "受付けました。要約を開始します。"
            else:
                reply_prefix = "受付けました。文字起こしを開始します。"
            reply_msg = f"{reply_prefix}\n\n{self.get_queue_status_text(user_id)}"
            self.sender.reply_text(reply_token, reply_msg)

        except Exception as e:
            logger.exception(e)
            self.sender.reply_text(reply_token, "音声受付中にエラーが発生しました。")

