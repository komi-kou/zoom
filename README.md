# Zoom録画議事録自動生成・Chatwork送信ツール

Zoomで録画した会議をGemini API 2.5 Proを通じて議事録を作成し、Chatworkのトークルームに自動送信するツールです。

## 機能

- Zoom APIを使用した録画ファイルの自動取得
- Gemini API 2.5 Proによる音声・動画からの議事録自動生成
- Chatwork APIを使用したトークルームへの自動送信
- 複数ユーザー対応（環境変数による設定管理）

## 必要なもの

### API認証情報

1. **Zoom API**
   - API Key
   - API Secret
   - Account ID（Server-to-Server OAuth使用時、オプション）

2. **Gemini API**
   - API Key

3. **Chatwork API**
   - API Token

### システム要件

- Python 3.8以上
- FFmpeg（動画処理用、Gemini APIが動画を直接処理できる場合は不要）

## セットアップ

### 1. リポジトリのクローン

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 3. 環境変数の設定

`.env`ファイルを作成し、以下の環境変数を設定してください：

```bash
# Zoom API設定
ZOOM_API_KEY=your_zoom_api_key
ZOOM_API_SECRET=your_zoom_api_secret
ZOOM_ACCOUNT_ID=your_zoom_account_id  # オプション（Server-to-Server OAuth使用時）

# Gemini API設定
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL_NAME=gemini-1.5-pro  # オプション（デフォルト: gemini-1.5-pro）

# Chatwork API設定
# ⚠️ 必須: APIトークンとトークルームIDの両方が必要です
CHATWORK_API_TOKEN=your_chatwork_api_token_here
DEFAULT_CHATWORK_ROOM_ID=your_default_room_id_here  # オプション（デフォルトルームID）
```

### 4. API認証情報の取得方法

#### Zoom API

1. [Zoom Marketplace](https://marketplace.zoom.us/)にアクセス
2. 「Develop」→「Build App」を選択
3. 「Server-to-Server OAuth」または「JWT」アプリを作成
4. API Key、API Secret、Account IDを取得

詳細: [Zoom API Documentation](https://marketplace.zoom.us/docs/api-reference/zoom-api)

#### Gemini API

1. [Google AI Studio](https://makersuite.google.com/app/apikey)にアクセス
2. APIキーを作成
3. APIキーをコピー

詳細: [Gemini API Documentation](https://ai.google.dev/docs)

#### Chatwork API

**⚠️ 重要: Chatwork API連携には2つの情報が必要です**
1. **APIトークン**（必須）: 認証用
2. **トークルームID**（必須）: メッセージ送信先

**APIトークンの取得方法:**
1. Chatworkにログイン
2. 右上の「利用者名」メニューをクリック
3. 「サービス連携」を選択
4. 「APIトークン」タブを選択
5. 「新しいAPIトークンを作成」をクリック
6. **重要**: トークンは一度だけ表示されます。必ずコピーして保存してください

**トークルームIDの取得方法:**
- **方法1**: トークルームを開く → 右上の歯車アイコン → 「グループチャットの設定」 → ルームIDをコピー
- **方法2**: トークルームのURLから取得（`https://www.chatwork.com/#!rid123456789` の場合、`123456789`がルームID）

詳細: [Chatwork API Documentation](https://developer.chatwork.com/docs)

## 使用方法

### 基本的な使用方法

```bash
python main.py <meeting_id> --room-id <room_id>
```

### パラメータ

- `meeting_id`（必須）: ZoomミーティングID
- `--room-id`（オプション）: ChatworkルームID（指定しない場合は環境変数のデフォルト値を使用）
- `--output-dir`（オプション）: 一時ファイル保存先ディレクトリ（デフォルト: ./temp）

### 使用例

```bash
# 環境変数のデフォルトルームIDを使用
python main.py 123456789

# ルームIDを指定
python main.py 123456789 --room-id 123456

# 一時ファイル保存先を指定
python main.py 123456789 --room-id 123456 --output-dir /tmp/zoom_recordings
```

## 処理フロー

1. **Zoom APIで録画ファイルを取得**
   - 指定されたミーティングIDの録画情報を取得
   - 録画ファイルをダウンロード

2. **Gemini APIで議事録を生成**
   - 録画ファイル（動画または音声）をGemini APIに送信
   - 音声認識と要約を行い、議事録を生成

3. **Chatworkに送信**
   - 生成された議事録をChatworkのトークルームに送信
   - 長いメッセージは自動的に分割

4. **一時ファイルの削除**
   - 処理完了後、ダウンロードした録画ファイルを削除

## 注意事項

- **API利用制限**: 各APIには利用制限があります。大量の処理を行う場合は、レート制限に注意してください。
- **セキュリティ**: `.env`ファイルには機密情報が含まれます。Gitにコミットしないよう注意してください。
- **ファイルサイズ**: 大きな録画ファイルの場合、処理に時間がかかる場合があります。
- **Chatworkメッセージ制限**: Chatworkのメッセージは約2-3万字が上限です。長い議事録は自動的に分割されます。

## トラブルシューティング

### 録画ファイルが見つからない

- ミーティングIDが正しいか確認してください
- 録画が完了しているか確認してください（Zoomのクラウド録画が有効になっている必要があります）

### API認証エラー

- 環境変数が正しく設定されているか確認してください
- APIキーやトークンが有効か確認してください

### Gemini APIエラー

- APIキーが正しく設定されているか確認してください
- ファイルサイズが制限を超えていないか確認してください

### Chatwork送信エラー

**エラー: "CHATWORK_API_TOKENが設定されていません"**
- `.env`ファイルに`CHATWORK_API_TOKEN`が設定されているか確認
- 環境変数名が正しいか確認（大文字小文字を区別）
- `.env`ファイルがプロジェクトルートにあるか確認

**エラー: "APIトークンが無効です"**
- APIトークンが正しくコピーされているか確認
- トークンに余分なスペースや改行が含まれていないか確認
- Chatworkの「サービス連携」→「APIトークン」でトークンを再生成

**エラー: "ルームIDが正しいか確認"**
- トークルームIDが正しいか確認（数字のみ）
- ルームURLから`rid`の後の数字を確認
- そのルームにアクセス権限があるか確認（ルームメンバーである必要があります）

## ライセンス

このプロジェクトのライセンス情報を記載してください。

## 貢献

プルリクエストやイシューの報告を歓迎します。

