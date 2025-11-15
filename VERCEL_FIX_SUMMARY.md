# Vercelデプロイ修正サマリー

## 🔍 問題の原因

Vercelのログに「Error importing app.py」というエラーが表示されていました。原因は以下の通りです：

1. **`auto_process_config`のモジュールレベル初期化**
   - `app.py`のインポート時に`AutoProcessConfig()`が実行されていた
   - Vercelでは`/tmp`ディレクトリが存在しない可能性があり、エラーが発生していた

2. **テンプレートと静的ファイルのパス**
   - 絶対パスを使用していたが、エラーハンドリングが不十分だった

3. **設定ファイルの保存先**
   - `/tmp`ディレクトリが存在しない場合にエラーが発生していた

## ✅ 実施した修正

### 1. `app.py`の修正

#### `auto_process_config`の遅延初期化
- モジュールレベルでの`auto_process_config = AutoProcessConfig()`を削除
- `get_auto_process_config()`関数を追加して遅延初期化を実装
- すべての`auto_process_config`の使用箇所を`get_auto_process_config()`に置き換え

#### テンプレートと静的ファイルの設定改善
- ディレクトリの存在確認を追加
- エラーハンドリングを改善
- フォールバック処理を追加

#### `index`エンドポイントの改善
- テンプレートが設定されていない場合のエラーハンドリングを追加

### 2. `scheduler.py`の修正

#### `AutoProcessConfig.__init__`の改善
- `/tmp`ディレクトリが存在しない場合に作成を試みる
- エラーハンドリングを改善

### 3. `config.py`の修正（以前の修正）

- 環境変数から直接読み込むように変更
- `.env`ファイルはローカル開発時のみ使用

## 📋 修正内容の詳細

### `app.py`の変更点

1. **遅延初期化の実装**
```python
# 変更前
auto_process_config = AutoProcessConfig()

# 変更後
_auto_process_config: Optional[AutoProcessConfig] = None

def get_auto_process_config() -> AutoProcessConfig:
    """AutoProcessConfigインスタンスを取得（遅延初期化）"""
    global _auto_process_config
    if _auto_process_config is None:
        try:
            _auto_process_config = AutoProcessConfig()
        except Exception as e:
            logger.warning(f"AutoProcessConfigの初期化に失敗（初回起動時は正常）: {e}")
            _auto_process_config = AutoProcessConfig()
    return _auto_process_config
```

2. **すべての使用箇所を置き換え**
- `add_auto_process_mapping`: `get_auto_process_config().add_mapping(...)`
- `remove_auto_process_mapping`: `get_auto_process_config().remove_mapping(...)`
- `get_auto_process_mappings`: `get_auto_process_config().get_all_mappings()`
- `zoom_webhook`: `get_auto_process_config().add_mapping(...)`
- `process_meeting_recording_task`: `get_auto_process_config().mark_as_processed(...)`
- `check_and_process_automatically`: `get_auto_process_config()`を使用
- `process_new_recording`: `get_auto_process_config()`を使用

### `scheduler.py`の変更点

```python
def __init__(self):
    # Vercelでは/tmpディレクトリを使用
    import os
    temp_dir = os.environ.get("TEMP_DIR", "/tmp")
    config_dir = Path(temp_dir)
    # ディレクトリが存在しない場合は作成
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"設定ディレクトリの作成に失敗（初回起動時は正常）: {e}")
    self.config_file = config_dir / self.CONFIG_FILE
    self.config: Dict[str, Dict] = {}
    self.load_config()
```

## 🚀 デプロイ手順

1. **修正をGitHubにプッシュ**
   ```bash
   git add .
   git commit -m "Fix Vercel deployment: lazy initialization and error handling"
   git push
   ```

2. **Vercelが自動的に再デプロイ**
   - GitHubにプッシュすると、Vercelが自動的に再デプロイを開始します

3. **デプロイ完了後、再度アクセス**
   - `https://zoom-black.vercel.app`にアクセス
   - エラーが解消されているか確認

4. **まだエラーが発生する場合**
   - Vercelのログを確認
   - エラーメッセージを共有してください

## ⚠️ 注意事項

- **環境変数の設定**
  - Vercelダッシュボード → Settings → Environment Variables
  - すべての環境変数が設定されているか確認
  - `TEMP_DIR`は`/tmp`に設定してください

- **`requirements.txt`の確認**
  - すべての依存関係が含まれているか確認

- **`vercel.json`の確認**
  - `maxDuration`が60秒に設定されているか確認

## 📝 確認事項チェックリスト

- [x] `auto_process_config`の遅延初期化を実装
- [x] すべての`auto_process_config`の使用箇所を`get_auto_process_config()`に置き換え
- [x] テンプレートと静的ファイルの設定を改善
- [x] `scheduler.py`の`__init__`を改善
- [x] エラーハンドリングを追加
- [ ] GitHubに修正をプッシュ
- [ ] Vercelが再デプロイを完了
- [ ] デプロイ後の動作確認

