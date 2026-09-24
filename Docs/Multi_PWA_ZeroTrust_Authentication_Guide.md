# Project_ALICE マルチPWA共通認証・アクセス設計仕様書

> **【目的】**  
> `project-alice.net` 配下で運用するすべてのPWAサービス（ALICEコックピット、Wake on LAN操作画面、その他Webツール）に対し、**アプリ側の自前認証実装をゼロ**にしつつ、**「日常0秒スルー ＆ 外部鉄壁防御」** を共通適用するための標準設計書。

---

## 1. 全体アーキテクチャ & ドメイン設計

すべてのPWAは **「サブドメイン分離方式」** で運用する。

| サブドメイン | サービス名 | 稼働場所 / ポート | 認証方式 (Cloudflare Access) | PWAアイコン |
| :--- | :--- | :--- | :--- | :--- |
| **`admin.project-alice.net`** | **ALICE コックピット** | alice-server (`:8000`) | 自宅IP/WARP: Bypass, 外部: PIN 15分 | 🤖 ALICE |
| **`wol.project-alice.net`** | **Wake on LAN (WoL)** | タブレット / 別マシン (`:port`) | **同上（共通ポリシー適用）** | ⚡ PC電源 |
| **`[app].project-alice.net`** | **将来の別PWA** | 任意のマシン | **同上（共通ポリシー適用）** | 📱 各アプリ |
| **`project-alice.net`** | **LINE Webhook / 共有** | alice-server (`:8000`) | **認証なし（完全オープン）** | （PWAなし） |

### サブドメイン分離にする理由
1. **PWAの完全独立性**: PWAはオリジン（ドメイン）単位で別アプリとして端末に保存される。サブドメインを分けることで、アプリアイコン・キャッシュ・Service Workerが競合せず、複数アプリを並べて快適に利用できる。
2. **ルーティングの柔軟性**: Cloudflare Tunnel を介して、同じ自宅LAN内にある別端末（タブレットやラズパイ）へサブドメイン単位で直接パケットを流せる。

---

## 2. デバイス別アクセス制御マトリクス（共通ルール）

どのPWAサービスであっても、以下の統一されたアクセス体験を提供する。

```text
                                  ┌─► [自宅Wi-Fi IP] ──────► ⚡ 0秒スルー (Bypass)
[アクセス元] ──► Cloudflare Access ┼─► [Pixel 10 (WARP)] ──► ⚡ 0秒スルー (Bypass)
                                  └─► [その他外部端末] ────► 🔒 One-time PIN (15分セッション)

[モバイルPC] ──► Tailscale (Tailnet) 直結 ────────────────► ⚡ 0秒スルー (Cloudflare介さず直結)
```

| 端末 / 環境 | アクセス経路 / URL | 認証挙動 | ユーザー体験 |
| :--- | :--- | :--- | :---: |
| **📱 スマホ (Pixel 10)** | `https://[app].project-alice.net`<br>（ホーム画面のPWAアイコン） | **Cloudflare One (WARP) 判定**<br>※自宅でも外の4G/5Gでも有効 | **完全0秒スルー**<br>（タップ即起動） |
| **💻 モバイルPC (外出先)** | `http://[端末ホスト名]:[port]/` | **Tailscale (Tailnet) 直結**<br>※Cloudflareを通さない | **完全0秒スルー** |
| **🖥️ メインPC (自宅)** | `https://[app].project-alice.net` | **自宅IP (180.196.23.177) 判定** | **完全0秒スルー** |
| **🚨 緊急時 / 登録外端末** | `https://[app].project-alice.net` | **One-time PIN (メール認証)** | **15分だけ安全作業**<br>（自動失効） |

---

## 3. 新しいPWA（WoL等）を追加する時の展開レシピ（4ステップ）

新しいPWA（例: Wake on LAN）を立ち上げる際は、以下の手順通りに進めるだけで認証基盤が完成する。

### ステップ①：Webアプリ側の実装（認証コードは実装不要！）
- **重要**: アプリ側でログイン画面、パスワード認証、MFA、セッション管理などを**自前実装する必要は一切ない**。
- 認証はすべて手前の Cloudflare エッジで完了しているため、アプリは純粋に機能（ボタンを押したらWoLパケットを送る等）だけを実装すればよい。

### ステップ②：Cloudflare Tunnel へのルーティング追加
1. Cloudflare Zero Trust ➔ `Networks` ➔ `Tunnels` ➔ 既存トンネルの `Configure` を開く。
2. `Public Hostname` ➔ `Add a public hostname`:
   - **Subdomain**: `wol`（任意の名前）
   - **Domain**: `project-alice.net`
   - **Type**: `HTTP`
   - **URL**: `192.168.1.xxx:port`（WoLを動かしているタブレット/別マシンのLAN内IPとポート）
     *※alice-serverのトンネルから同じLAN内の別端末へ直接中継可能！*

### ステップ③：Cloudflare Access ポリシーの割り当て
1. Cloudflare Zero Trust ➔ `Access` ➔ `Applications` ➔ `Add an application` (`Self-hosted`)。
2. **Application Configuration**:
   - Name: `Wake on LAN PWA`
   - Domain: `wol.project-alice.net`
   - Session Duration: `15 minutes`
3. **Policies**:
   - **ルール1**: Action = `Bypass`, Include = `IP ranges: 180.196.23.177/32`
   - **ルール2**: Action = `Bypass`, Include = `WARP`
   - **ルール3**: Action = `Allow`, Include = `Emails: (あなたのメールアドレス)`

### ステップ④：スマホへのPWAインストール
1. Pixel 10（WARP有効時）でブラウザを開き、`https://wol.project-alice.net` にアクセス。
2. 認証画面なしで0秒で操作画面が開くことを確認。
3. ブラウザメニューから「ホーム画面に追加」（PWAインストール）。
4. ホーム画面に独立した「WoL」アイコンが完成！

---

## 4. 運用・保守の注意点 (Tips)

1. **自宅のグローバルIPが変動した場合**:
   - プロバイダの都合等で自宅のグローバルIPが変わった場合、Cloudflare Access の `Bypass Home` ポリシーの IP を新しいIP（`curl ifconfig.me` で確認）に更新する。
   - ※Pixel 10 は WARP 認証のため、自宅IPが変わっても影響を受けず常に0秒スルー可能。
2. **Tailscale直結アクセスの注意**:
   - モバイルPCから直接アクセスする場合は、各端末（alice-serverやタブレット）のTailscale IPまたはMagicDNS（例: `http://tablet-wol:5000`）を指定する。
