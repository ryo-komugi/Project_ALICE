# ADR 008: 管理コックピットにおける自前MFA・デバイス管理の撤去と Cloudflare Zero Trust 境界認証の採択

> Status: Accepted  
> Date: 2026-09-20  
> Deciders: Project_ALICE Core Architecture Team  

---

## 1. 背景と課題 (Context)

`ALICE_Core` の管理コックピット（Admin Web UI）の保護のため、これまで以下の自前セキュリティ機構を開発・運用してきた：
1. **自前デバイス管理 (`devices.db`)**: 端末ごとのフィンガープリント、初回承認制、180日保持 Cookie。
2. **Discord `#alerts` ワンタップ MFA / モーダル承認**: 未承認端末からのアクセス時に 5分間有効なトークンを発行し、Discord 経由で承認。
3. **Tailnet / LAN 条件付きアクセス**: 接続元 IP / ネットワークに応じたバイパス。

しかし、実運用を進める中で以下の重大な課題が生じた：
- **アプリ層コードの過剰な複雑化**: FastAPI 内部でデバイス永続化、Cookie 検証、Web Push、MFA セッション失効などを抱え込み、テストケースや依存ライブラリ（`pywebpush` 等）が肥大化。
- **PWA・ブラウザ互換性の摩擦**: iOS / Android PWA での Cookie 保持やキャッシュ挙動と自前セッション判定の間でエッジケースが発生。
- **インフラ層との責務重複**: すでに外部公開トンネルとして **Cloudflare Tunnel (`cloudflared`)** を使用しており、ネットワーク境界（Edge）でのアクセス制御が可能な状態であった。

---

## 2. 決定事項 (Decision)

アプリ層での自前デバイス管理・自前 MFA を完全撤去し、**Cloudflare Zero Trust (Cloudflare Access)** によるネットワーク境界認証に一本化することを決定した。

### 1. 自前認証コードの完全撤去
- `devices.db`, `models/device.py`, `repository/device_repository.py`, `core/mfa_manager.py` および自前認証用エンドポイント（`/admin/login`, `/admin/mfa/*` 等）を完全削除。
- アプリケーションはセッション管理・デバイス承認の責務から解放され、コア機能（Job 管理・モニタリング）に集中する。

### 2. 境界認証（Cloudflare Access）の強制
- 管理画面へのアクセスは専用サブドメイン **`admin.project-alice.net`** に限定。
- Apex ドメイン（`project-alice.net/admin`）への直接アクセスは FastAPI 側で 404 遮断し、必ず Cloudflare Access の保護下にあるサブドメインを経由させる。
- `admin_auth.py` は、Cloudflare Access が付与する検証ヘッダー（`CF-Access-Authenticated-User-Email` 等）を検証するシンプルなガードとしてリファクタリング。

### 3. ログアウト処理の連携
- `/admin/logout` 呼び出し時は、Cloudflare Access のセッションログアウトエンドポイント（`https://<team>.cloudflareaccess.com/cdn-cgi/access/logout`）へリダイレクトし、境界側でセッションを確実に破棄。

---

## 3. 影響と評価 (Consequences)

### メリット
- **コードの大幅スリム化**: `ALICE_Core` から 6,000 行以上の認証・UI 関連コードを削減し、保守性と堅牢性が劇的に向上。
- **強固なエンタープライズセキュリティ**: Cloudflare 側の FIDO2 / WebAuthn（Passkey）、Google Workspace 認証、国別・IP 制限などの高度なポリシーをコード変更なしに即時利用可能。
- **PWA の安定動作**: 各端末（Pixel 10、iOS 等）の PWA において Cookie 不整合によるループやセッション切断が解消。

### デメリット / 制約事項
- Cloudflare Zero Trust のサービス稼働に依存する（ただし Tunnel 経由での公開が前提であるため実質的な追加リスクはない）。
