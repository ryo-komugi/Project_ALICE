"""
ALICE_Core LINE Gateway Adapter
LINE Messaging API の Webhook 受信、署名検証、コンテンツ受信、セッション管理、
リッチメニュー制御、およびイベントディスパッチを担当する外付けインターフェースアダプタ。

将来の脱LINE・別インターフェース（Discord, Web UI Direct, Slack 等）への移行を考慮し、
Hub (ジョブキュー/ワーカー実行エンジン) とは疎結合に設計されています。
"""
