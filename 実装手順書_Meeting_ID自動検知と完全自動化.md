# 実装手順書: Meeting ID自動検知と完全自動化

## 📋 実装目的

Zoom Meeting IDが発行された時点で自動検知し、録画完了時に自動的に議事録を生成してChatworkに送信する完全自動化機能を実装する。

## ✅ 既存機能の維持

以下の機能は完全に維持する：
- ✅ API設定機能（Zoom、Gemini、Chatwork）
- ✅ 手動での議事録生成機能
- ✅ 最近のミーティングから選択機能
- ✅ 自動処理設定のマッピング機能
- ✅ その他の既存機能

## 🎯 実装内容

### 1. `meeting.created`イベントの処理（Webhook方式）

**実装箇所**: `app.py`の`zoom_webhook`関数

**実装内容**:
- `meeting.created`イベントを受信した際に、Meeting IDを自動処理設定に追加
- デフォルトルームIDがあれば、それを使用して自動処理設定に追加
- ミーティングトピックも保存

**実装コード**:
```python
if event_type == "meeting.created":
    payload = data.get("payload", {})
    object_data = payload.get("object", {})
    meeting_id = str(object_data.get("id"))
    meeting_topic = object_data.get("topic", f"ミーティング {meeting_id}")
    
    logger.info(f"ミーティング作成を検知: ミーティングID={meeting_id}, トピック={meeting_topic}")
    
    # デフォルトルームIDがあれば自動処理設定に追加
    if settings and settings.default_chatwork_room_id:
        auto_process_config.add_mapping(meeting_id, settings.default_chatwork_room_id, meeting_topic)
        logger.info(f"自動処理設定を追加: ミーティングID={meeting_id}, ルームID={settings.default_chatwork_room_id}")
    else:
        logger.info(f"デフォルトルームIDが設定されていないため、自動処理設定を追加しませんでした: ミーティングID={meeting_id}")
```

### 2. デフォルトルームIDによる完全自動化

#### 2-1. Webhookエンドポイントの修正

**実装箇所**: `app.py`の`zoom_webhook`関数（`recording.completed`イベント処理部分）

**実装内容**:
- 自動処理設定にマッピングがない場合でも、デフォルトルームIDがあれば自動処理
- 既存のロジックを拡張

**実装コード**:
```python
# 自動処理設定を確認（デフォルトルームIDも考慮）
room_id = auto_process_config.get_room_id(meeting_id)
if not room_id and settings and settings.default_chatwork_room_id:
    room_id = settings.default_chatwork_room_id
    logger.info(f"デフォルトルームIDを使用: ミーティングID={meeting_id}, ルームID={room_id}")

if room_id and not auto_process_config.is_processed(meeting_id):
    # 自動処理を開始
    task_id = str(uuid.uuid4())
    asyncio.create_task(
        process_meeting_recording_task(task_id, meeting_id, room_id)
    )
    auto_process_config.mark_as_processed(meeting_id)
    
    return JSONResponse({
        "success": True,
        "message": f"自動処理を開始しました: ミーティングID={meeting_id}"
    })
else:
    logger.info(f"自動処理設定がないか、既に処理済み: ミーティングID={meeting_id}")
    return JSONResponse({
        "success": True,
        "message": "自動処理設定がありません"
    })
```

#### 2-2. スケジューラーの修正

**実装箇所**: `app.py`の`check_and_process_automatically`関数

**実装内容**:
- 自動処理設定にマッピングがない場合でも、デフォルトルームIDがあれば自動処理
- 既存のロジックを拡張

**実装コード**:
```python
# 自動処理設定を確認（デフォルトルームIDも考慮）
room_id = auto_process_config.get_room_id(meeting_id)
if not room_id and settings and settings.default_chatwork_room_id:
    room_id = settings.default_chatwork_room_id
    logger.info(f"デフォルトルームIDを使用: ミーティングID={meeting_id}, ルームID={room_id}")

if room_id and not auto_process_config.is_processed(meeting_id):
    logger.info(f"自動処理を開始: ミーティングID={meeting_id}, ルームID={room_id}")
    
    # 処理を開始
    task_id = str(uuid.uuid4())
    
    try:
        # 処理を実行して結果を待つ
        result = await process_meeting_recording_task(task_id, meeting_id, room_id)
        
        # 成功した場合のみ処理済みマークを付ける
        if result.get("success"):
            auto_process_config.mark_as_processed(meeting_id)
            logger.info(f"✅ 自動処理が完了しました: ミーティングID={meeting_id}")
        else:
            logger.error(f"❌ 自動処理が失敗しました: ミーティングID={meeting_id}, エラー: {result.get('error', '不明なエラー')}")
            # 失敗した場合は処理済みマークを付けない（再処理の機会を残す）
    except Exception as e:
        logger.error(f"❌ 自動処理でエラーが発生しました: ミーティングID={meeting_id}, エラー: {e}", exc_info=True)
        # エラーが発生した場合は処理済みマークを付けない
```

## 📝 実装手順

### ステップ1: `meeting.created`イベントの処理を追加

1. `app.py`の`zoom_webhook`関数を確認
2. `recording.completed`イベント処理の前に、`meeting.created`イベント処理を追加
3. Meeting IDを自動処理設定に追加（デフォルトルームIDを使用）

### ステップ2: Webhookエンドポイントの修正

1. `app.py`の`zoom_webhook`関数の`recording.completed`イベント処理部分を修正
2. デフォルトルームIDによるフォールバック処理を追加

### ステップ3: スケジューラーの修正

1. `app.py`の`check_and_process_automatically`関数を修正
2. デフォルトルームIDによるフォールバック処理を追加

### ステップ4: 動作確認

1. Webhookエンドポイントが正しく動作するか確認
2. `meeting.created`イベントが正しく処理されるか確認
3. デフォルトルームIDによる自動処理が正しく動作するか確認
4. 既存機能が正しく動作するか確認

## 🔍 実装前の確認事項

### 既存機能の確認

- ✅ API設定機能（`/api/settings/save`）
- ✅ 手動での議事録生成機能（`/api/process`）
- ✅ 最近のミーティングから選択機能（`/api/meetings/recent`）
- ✅ 自動処理設定のマッピング機能（`/api/auto-process/mapping`）
- ✅ Webhookエンドポイント（`/api/webhook/zoom`）
- ✅ スケジューラー（`check_and_process_automatically`）

### 設定値の確認

- ✅ `DEFAULT_CHATWORK_ROOM_ID`が設定されているか確認
- ✅ `settings.default_chatwork_room_id`が正しく読み込まれているか確認

## 🎯 実装後の動作フロー

### Webhook方式（推奨）

```
Zoomミーティング作成（打ち合わせA）
↓
Meeting IDが発行される（例: 123456789）
↓
meeting.created イベントを受信
↓
Meeting IDを検知（123456789）
↓
Meeting IDを自動処理設定に追加（デフォルトルームIDを使用）
↓
ミーティング終了
↓
クラウド録画が完了
↓
recording.completed イベントを受信
↓
自動処理設定からルームIDを取得（デフォルトルームID）
↓
自動処理開始
↓
録画ファイルを取得（Zoom API）
↓
Gemini APIで議事録を生成
↓
Chatworkに送信（デフォルトルームIDに送信）
```

### ポーリング方式（既存機能）

```
スケジューラー起動（60秒ごと）
↓
録画付きミーティングを取得
↓
自動処理設定を確認（デフォルトルームIDも考慮）
↓
自動処理開始
↓
録画ファイルを取得（Zoom API）
↓
Gemini APIで議事録を生成
↓
Chatworkに送信（デフォルトルームIDに送信）
```

## ⚠️ 注意事項

1. **既存機能の維持**: 既存の機能は一切変更しない
2. **デフォルトルームIDの設定**: デフォルトルームIDが設定されていない場合、自動処理設定に追加されない
3. **エラーハンドリング**: エラーが発生した場合でも、既存機能に影響を与えないようにする
4. **ログ出力**: デバッグしやすいように、適切なログを出力する

## 📊 実装後の確認項目

- ✅ `meeting.created`イベントが正しく処理されるか
- ✅ デフォルトルームIDによる自動処理が正しく動作するか
- ✅ 既存機能が正しく動作するか
- ✅ エラーハンドリングが正しく動作するか
- ✅ ログ出力が適切か

