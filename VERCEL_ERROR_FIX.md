# Vercelエラー修正ガイド

## 🔴 エラー内容

```
500: INTERNAL_SERVER_ERROR
Code: FUNCTION_INVOCATION_FAILED
```

## 🔍 考えられる原因

1. **環境変数が設定されていない**
   - Zoom、Gemini、ChatworkのAPIキーが設定されていない
   - `config.py`で必須フィールドがエラーを発生させている

2. **起動時のエラー**
   - `startup_event`でエラーが発生している
   - 一時ディレクトリの作成に失敗している

3. **依存関係の問題**
   - `requirements.txt`に必要なパッケージが含まれていない

## ✅ 修正手順

### 1. Vercelのログを確認

1. Vercelダッシュボードにログイン
2. プロジェクト「zoom」を選択
3. 「Deployments」タブを開く
4. 最新のデプロイメントをクリック
5. 「Functions」タブを開く
6. 「View Function Logs」をクリック
7. エラーメッセージを確認

### 2. 環境変数の設定確認

Vercelダッシュボードで以下を確認：

1. 「Settings」→「Environment Variables」を開く
2. 以下の環境変数がすべて設定されているか確認：
   - `ZOOM_API_KEY`
   - `ZOOM_API_SECRET`
   - `ZOOM_ACCOUNT_ID`
   - `GEMINI_API_KEY`
   - `GEMINI_MODEL_NAME`（オプション、デフォルト: `gemini-2.5-pro`）
   - `CHATWORK_API_TOKEN`
   - `DEFAULT_CHATWORK_ROOM_ID`（オプション）
   - `TEMP_DIR`（推奨: `/tmp`）

3. 環境変数が設定されていない場合は、追加してください

### 3. コードの修正

以下の修正を適用しました：

1. **起動時のエラーハンドリングを改善**
   - `startup_event`でエラーが発生してもアプリケーションが起動を続けるように修正
   - 一時ディレクトリの作成を確実にする

2. **`vercel.json`の修正**
   - `maxDuration`を60秒に設定（長時間処理に対応）

3. **テンプレート読み込みのエラーハンドリング**
   - テンプレート読み込みエラー時のフォールバックを追加

### 4. 再デプロイ

1. GitHubに修正をプッシュ
2. Vercelが自動的に再デプロイを開始
3. デプロイが完了するまで待機
4. 再度アクセスして確認

## 🔧 トラブルシューティング

### 環境変数が設定されていない場合

エラーログに以下のようなメッセージが表示される可能性があります：
```
ValidationError: Field required
```

この場合、Vercelの「Settings」→「Environment Variables」で環境変数を設定してください。

### 依存関係の問題

エラーログに以下のようなメッセージが表示される可能性があります：
```
ModuleNotFoundError: No module named 'xxx'
```

この場合、`requirements.txt`に必要なパッケージが含まれているか確認してください。

### タイムアウトエラー

長時間かかる処理でタイムアウトが発生する場合：
- `vercel.json`の`maxDuration`を確認（現在60秒に設定）
- Proプラン以上では最大300秒まで設定可能

## 📝 確認事項

- [ ] 環境変数がすべて設定されている
- [ ] `vercel.json`が正しく設定されている
- [ ] `requirements.txt`に必要なパッケージが含まれている
- [ ] GitHubに最新のコードがプッシュされている
- [ ] Vercelのログでエラー詳細を確認した

