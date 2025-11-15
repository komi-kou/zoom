# Zoom議事録自動生成ツール - Webアプリケーション版

## 🚀 クイックスタート

### 1. 依存パッケージのインストール

```bash
# 仮想環境を作成（初回のみ）
python3 -m venv venv

# 仮想環境を有効化
source venv/bin/activate  # macOS/Linux
# または
venv\Scripts\activate  # Windows

# 依存パッケージをインストール
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env`ファイルを作成し、以下の環境変数を設定してください：

```bash
# Zoom API設定
ZOOM_API_KEY=your_zoom_api_key
ZOOM_API_SECRET=your_zoom_api_secret
ZOOM_ACCOUNT_ID=your_zoom_account_id  # オプション

# Gemini API設定
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL_NAME=gemini-1.5-pro  # オプション

# Chatwork API設定
CHATWORK_API_TOKEN=your_chatwork_api_token
DEFAULT_CHATWORK_ROOM_ID=your_default_room_id  # オプション
```

### 3. サーバーの起動

```bash
# 仮想環境を有効化
source venv/bin/activate  # macOS/Linux
# または
venv\Scripts\activate  # Windows

# サーバーを起動
python run.py
```

### 4. ブラウザでアクセス

サーバー起動後、以下のURLにアクセスしてください：

```
http://localhost:8000
```

## 📱 使い方

### ステップ1: API接続テスト

1. ページ上部の「API接続テスト」セクションで、各APIの接続をテストできます
2. 「Zoom API テスト」「Gemini API テスト」「Chatwork API テスト」ボタンをクリック
3. 緑色のメッセージが表示されれば接続成功です

### ステップ2: 議事録生成

1. 「ZoomミーティングID」に録画されたミーティングのIDを入力
2. 「ChatworkルームID」に送信先のルームIDを入力
3. 「議事録を生成して送信」ボタンをクリック
4. 進捗バーで処理状況を確認できます
5. 処理が完了すると、Chatworkに議事録が自動送信されます

## 🎨 機能

- **美しいUI**: 初心者でも使いやすい直感的なデザイン
- **リアルタイム進捗表示**: 処理の進捗をリアルタイムで確認
- **API接続テスト**: 各APIの接続状態を簡単に確認
- **エラーハンドリング**: エラーが発生した場合も分かりやすいメッセージを表示
- **レスポンシブデザイン**: スマートフォンやタブレットでも快適に使用可能

## 🔧 技術スタック

- **バックエンド**: FastAPI
- **フロントエンド**: HTML5, CSS3, JavaScript (Vanilla JS)
- **UIデザイン**: モダンなグラデーションとカード型レイアウト
- **非同期処理**: 長時間処理もブロックしない非同期処理

## 📦 デプロイ

### Herokuへのデプロイ

1. `Procfile`を作成：
```
web: uvicorn app:app --host 0.0.0.0 --port $PORT
```

2. Herokuにデプロイ：
```bash
heroku create your-app-name
git push heroku main
heroku config:set ZOOM_API_KEY=your_key
heroku config:set ZOOM_API_SECRET=your_secret
heroku config:set GEMINI_API_KEY=your_key
heroku config:set CHATWORK_API_TOKEN=your_token
```

### Dockerでのデプロイ

`Dockerfile`を作成：
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 🐛 トラブルシューティング

### サーバーが起動しない

- ポート8000が使用されている場合は、環境変数`PORT`で別のポートを指定できます
- 仮想環境が有効化されているか確認してください

### API接続テストが失敗する

- `.env`ファイルが正しく設定されているか確認してください
- 各APIの認証情報が正しいか確認してください

### 議事録が生成されない

- ZoomミーティングIDが正しいか確認してください
- 録画が完了しているか確認してください
- ログを確認してエラーメッセージを確認してください

## 📝 ライセンス

このプロジェクトのライセンス情報を記載してください。


