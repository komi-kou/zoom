# API連携完全ガイド

## 📋 全体の連携フロー

```
Zoomミーティング終了
    ↓
Zoom APIで録画ファイルを取得（ミーティングID使用）
    ↓
Gemini APIで録画内容を解析・議事録生成
    ↓
Chatwork APIで議事録を送信
    ↓
完了！
```

## 🔑 必要な認証情報

### 1. Zoom API

#### 必要な情報
- ✅ **ZOOM_API_KEY**: Zoom Marketplaceで取得
- ✅ **ZOOM_API_SECRET**: Zoom Marketplaceで取得
- ✅ **ZOOM_ACCOUNT_ID**: Server-to-Server OAuth使用時（オプション）

#### 取得方法
1. [Zoom Marketplace](https://marketplace.zoom.us/)にアクセス
2. 「Develop」→「Build App」を選択
3. 「Server-to-Server OAuth」または「JWT」アプリを作成
4. API Key、API Secret、Account IDを取得

#### エンドポイント
- ✅ `GET /meetings/{meetingId}/recordings` - 録画情報取得
- ✅ ミーティングIDだけで録画を取得可能

### 2. Gemini API

#### 必要な情報
- ✅ **GEMINI_API_KEY**: Google AI Studioで取得
- ✅ **GEMINI_MODEL_NAME**: gemini-2.5-pro（デフォルト）

#### 取得方法
1. [Google AI Studio](https://makersuite.google.com/app/apikey)にアクセス
2. APIキーを作成
3. APIキーをコピー

#### 使用制限
- ✅ **Gemini 2.5 Pro**: 1日100回まで無料（1日5回なら余裕）
- ✅ ファイルアップロードに対応
- ✅ 動画・音声ファイルの処理に対応

### 3. Chatwork API

#### 必要な情報
- ✅ **CHATWORK_API_TOKEN**（必須）: Chatworkの「サービス連携」で取得
- ✅ **トークルームID**（必須）: 送信先のトークルームID

**⚠️ 重要**: Chatwork API連携には**APIトークンとトークルームIDの両方**が必要です。

#### APIトークンの取得方法

1. Chatworkにログイン
2. 右上の「利用者名」メニューをクリック
3. 「サービス連携」を選択
4. 「APIトークン」タブを選択
5. 「新しいAPIトークンを作成」をクリック（または既存のトークンを確認）
6. **重要**: トークンは一度だけ表示されます。必ずコピーして安全な場所に保存してください
7. トークンをコピー（例: `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`）

#### トークルームIDの取得方法

**方法1: ルーム設定から取得**
1. 送信したいトークルームを開く
2. 右上の歯車アイコン（⚙️）をクリック
3. 「グループチャットの設定」または「ルーム設定」を選択
4. 「ルームID」を確認・コピー（数字のみ、例: `123456789`）

**方法2: URLから取得**
1. トークルームを開く
2. ブラウザのURLバーを確認
3. URL形式: `https://www.chatwork.com/#!rid123456789`
4. `rid`の後の数字（`123456789`）がルームIDです

#### エンドポイント
- ✅ `GET /me` - 自分の情報取得（接続テスト用）
- ✅ `GET /rooms/{room_id}` - ルーム情報取得
- ✅ `POST /rooms/{room_id}/messages` - メッセージ送信
- ✅ 認証: `X-ChatWorkToken` ヘッダー
- ✅ パラメータ: `body`（メッセージ本文）

#### 注意事項
- **APIトークンとトークルームIDは両方必要です**
- APIトークンがないと、トークルームIDだけでは連携できません
- トークルームIDがないと、メッセージの送信先が分かりません
- APIトークンは機密情報です。他人に共有しないでください
- ルームIDは、そのルームにアクセス権限がある必要があります

## ✅ 実装確認

### Zoom API連携 ✅
- ✅ ミーティングIDから録画情報を取得
- ✅ JWT認証とServer-to-Server OAuthに対応
- ✅ 録画ファイルのダウンロードに対応
- ✅ ダウンロードURLの認証処理を改善

### Gemini API連携 ✅
- ✅ APIキーによる認証
- ✅ 動画・音声ファイルのアップロード
- ✅ 議事録の自動生成
- ✅ 使用状況の追跡

### Chatwork API連携 ✅
- ✅ APIトークンによる認証
- ✅ 接続テスト機能（`test_connection()`メソッド）
- ✅ 自分の情報取得（`get_my_info()`メソッド）
- ✅ ルーム情報取得（`get_room_info()`メソッド）
- ✅ メッセージ送信
- ✅ 長文メッセージの自動分割
- ✅ エラーハンドリング（APIトークン未設定時の明確なエラーメッセージ）

## 🔧 環境変数の設定

`.env`ファイルに以下の環境変数を設定：

```bash
# Zoom API設定
ZOOM_API_KEY=your_zoom_api_key
ZOOM_API_SECRET=your_zoom_api_secret
ZOOM_ACCOUNT_ID=your_zoom_account_id  # オプション

# Gemini API設定
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL_NAME=gemini-2.5-pro  # デフォルト

# Chatwork API設定
CHATWORK_API_TOKEN=your_chatwork_api_token
DEFAULT_CHATWORK_ROOM_ID=your_default_room_id  # オプション
```

## 📝 各APIの連携確認

### Zoom API
- ✅ ミーティングIDだけで連携可能
- ✅ 録画情報の取得に対応
- ✅ 録画ファイルのダウンロードに対応

### Gemini API
- ✅ APIキーだけで連携可能
- ✅ 録画ファイルの処理に対応
- ✅ 議事録の生成に対応

### Chatwork API
- ✅ APIトークンとトークルームIDで連携可能
- ✅ 接続テスト機能でAPIトークンの検証が可能
- ✅ メッセージ送信に対応
- ✅ ルームIDで送信先を指定可能
- ✅ APIトークン未設定時の明確なエラーメッセージ

## 🎯 まとめ

**すべてのAPI連携が正しく実装されています！**

- ✅ Zoom API: ミーティングIDで録画取得
- ✅ Gemini API: 録画から議事録生成
- ✅ Chatwork API: 議事録を送信

各APIの認証情報を`.env`ファイルに設定すれば、すぐに使用できます。


