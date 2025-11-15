"""
Zoom録画議事録自動生成Webアプリケーション
FastAPIを使用したWeb UI
"""
import os
import uuid
import asyncio
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import requests
from config import get_settings
from zoom_client import ZoomClient
from gemini_client import GeminiClient
from chatwork_client import ChatworkClient
from scheduler import AutoProcessConfig
# 遅延インポート（ファイルシステムアクセスでブロッキングする可能性があるため）
# from local_recording_detector import LocalRecordingDetector
# from recording_watcher import RecordingWatcher
from fastapi import Body
import logging

# 使用状況追跡（オプション）
try:
    from usage_tracker import UsageTracker
    usage_tracker = UsageTracker()
except ImportError:
    usage_tracker = None

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# FastAPIアプリケーションの初期化
app = FastAPI(title="Zoom議事録自動生成ツール")

# テンプレートと静的ファイルの設定
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 設定の取得（エラーハンドリング付き）
_settings_loaded = False

def reload_settings():
    """設定を再読み込み"""
    global settings, _settings_loaded
    if _settings_loaded:
        # 既に読み込み済みの場合は再読み込みを試みる
        pass
    
    try:
        # 設定を再読み込み（.envファイルから最新の値を読み込む）
        settings = get_settings()
        logger.info("設定を再読み込みしました")
        
        # デバッグ用：設定値の確認
        if settings:
            logger.info(f"設定値確認:")
            logger.info(f"  ZOOM_API_KEY: {settings.zoom_api_key[:10] if settings.zoom_api_key else 'None'}... (長さ: {len(settings.zoom_api_key) if settings.zoom_api_key else 0})")
            logger.info(f"  ZOOM_API_SECRET: {settings.zoom_api_secret[:10] if settings.zoom_api_secret else 'None'}... (長さ: {len(settings.zoom_api_secret) if settings.zoom_api_secret else 0})")
            logger.info(f"  ZOOM_ACCOUNT_ID: {settings.zoom_account_id if settings.zoom_account_id else 'None'}")
        
        _settings_loaded = True
        return True
    except Exception as e:
        logger.error(f"設定の読み込みに失敗しました: {e}", exc_info=True)
        logger.error("環境変数が設定されているか確認してください")
        settings = None
        _settings_loaded = False
        return False

# 設定の読み込み（起動時に実行されるが、インポート時には実行しない）
settings = None
# reload_settings()  # インポート時のブロッキングを防ぐため、startup_eventで実行

# 処理中のタスクを管理
processing_tasks = {}

# 自動処理設定
auto_process_config = AutoProcessConfig()

# スケジューラー（後で初期化）
scheduler_task: Optional[asyncio.Task] = None

# 録画ファイル監視（後で初期化）
recording_watcher: Optional["RecordingWatcher"] = None


async def process_meeting_recording_task(
    task_id: str,
    meeting_id: str,
    room_id: str
) -> dict:
    """
    非同期で議事録生成処理を実行
    
    Args:
        task_id: タスクID
        meeting_id: ZoomミーティングID
        room_id: ChatworkルームID
        
    Returns:
        処理結果
    """
    if not settings:
        processing_tasks[task_id] = {
            "status": "error",
            "message": "設定が読み込まれていません",
            "result": {
                "success": False,
                "error": "環境変数が設定されていません"
            }
        }
        return processing_tasks[task_id]["result"]
    
    recording_file_path = None
    
    try:
        processing_tasks[task_id] = {"status": "processing", "progress": 0}
        
        # ========== ステップ1: Zoom文字起こしまたは録画ファイルを取得 ==========
        logger.info(f"[タスク {task_id}] Zoom録画/文字起こしを取得開始: ミーティングID={meeting_id}")
        processing_tasks[task_id]["progress"] = 10
        processing_tasks[task_id]["message"] = "Zoom文字起こしを確認中..."
        
        zoom_client = ZoomClient(
            api_key=settings.zoom_api_key,
            api_secret=settings.zoom_api_secret,
            account_id=settings.zoom_account_id
        )
        
        output_dir = settings.temp_dir
        os.makedirs(output_dir, exist_ok=True)
        
        import concurrent.futures
        loop = asyncio.get_event_loop()
        
        # ユーザーの要望: ローカル録画ファイルを優先、なければZoom API録画を使用
        # 優先順位: 1. ローカル録画 → 2. Zoom API録画（文字起こしは使用しない）
        transcript_text = None
        recording_file_path = None
        
        # ========== ステップ1-1: ローカル録画ファイルを検索 ==========
        logger.info(f"[タスク {task_id}] ローカル録画ファイルを検索開始（優先）")
        processing_tasks[task_id]["progress"] = 15
        processing_tasks[task_id]["message"] = "ローカル録画ファイルを検索中..."
        
        try:
            # 遅延インポート（ファイルシステムアクセスでブロッキングする可能性があるため）
            from local_recording_detector import LocalRecordingDetector
            detector = LocalRecordingDetector()
            
            # 録画保存先ディレクトリを取得（デバッグ用）
            recording_dir = detector.get_recording_directory()
            logger.info(f"[タスク {task_id}] 録画保存先ディレクトリ: {recording_dir}")
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # 期間制限なしでローカル録画を検索
                local_recording = await loop.run_in_executor(
                    executor,
                    detector.find_recording_by_meeting_id,
                    meeting_id,
                    None,  # 自動検出
                    None  # 期間制限なし（全ての録画を検索）
                )
                
                if local_recording:
                    recording_file_path = local_recording["path"]
                    logger.info(f"[タスク {task_id}] ローカル録画ファイルを発見: {recording_file_path}")
                    processing_tasks[task_id]["progress"] = 30
                    processing_tasks[task_id]["message"] = f"ローカル録画ファイルを発見（{local_recording['size_mb']:.2f}MB）"
                else:
                    # 最新の録画ファイルを使用（期間制限なし）
                    logger.info(f"[タスク {task_id}] ミーティングIDに一致する録画が見つからないため、最新の録画を検索します")
                    latest_recording = await loop.run_in_executor(
                        executor,
                        detector.find_latest_recording,
                        None,  # 自動検出
                        None,  # 期間制限なし（全ての録画を検索）
                        1.0  # 1MB以上
                    )
                    
                    if latest_recording:
                        recording_file_path = latest_recording["path"]
                        logger.info(f"[タスク {task_id}] 最新のローカル録画ファイルを使用: {recording_file_path}")
                        processing_tasks[task_id]["progress"] = 30
                        processing_tasks[task_id]["message"] = f"最新のローカル録画ファイルを使用（{latest_recording['size_mb']:.2f}MB）"
        except Exception as e:
            logger.warning(f"[タスク {task_id}] ローカル録画の検索に失敗: {e}")
            import traceback
            logger.warning(f"[タスク {task_id}] ローカル録画検索エラーの詳細: {traceback.format_exc()}")
        
        # ========== ステップ1-2: ローカル録画が見つからない場合はZoom API録画を取得 ==========
        if not recording_file_path:
            logger.info(f"[タスク {task_id}] ローカル録画が見つからないため、Zoom APIから録画を取得を試みます")
            processing_tasks[task_id]["progress"] = 20
            processing_tasks[task_id]["message"] = "Zoom APIから録画を取得中..."
            
            try:
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    recording_file_path = await loop.run_in_executor(
                    executor,
                    zoom_client.get_recording_file,
                    meeting_id,
                    output_dir
                    )
        
                if recording_file_path:
                    logger.info(f"[タスク {task_id}] Zoom APIから録画ファイルを取得しました: {recording_file_path}")
                    processing_tasks[task_id]["progress"] = 30
                    processing_tasks[task_id]["message"] = f"Zoom APIから録画ファイルを取得しました（{os.path.getsize(recording_file_path) / 1024 / 1024:.2f}MB）"
            except Exception as e:
                error_msg = str(e)
                # 404エラーの場合は詳細を記録
                if "404" in error_msg:
                    logger.warning(f"[タスク {task_id}] Zoom APIからの録画取得に失敗（404）: ミーティングID={meeting_id} に録画が見つかりません")
                else:
                    logger.warning(f"[タスク {task_id}] Zoom APIからの録画取得に失敗: {e}")
                recording_file_path = None
        
        # 録画ファイルが見つからない場合
        if not recording_file_path:
            # 録画保存先ディレクトリの情報を取得
            try:
                from local_recording_detector import LocalRecordingDetector
                detector = LocalRecordingDetector()
                recording_dir = detector.get_recording_directory()
                recording_dir_str = str(recording_dir) if recording_dir else "見つかりませんでした"
                
                # 全ての録画ファイルを検索して、見つかった録画の数を確認
                all_recordings = detector.find_recordings(hours=None, min_size_mb=1.0)
                recordings_count = len(all_recordings)
            except Exception as e:
                recording_dir_str = f"取得に失敗しました: {str(e)}"
                recordings_count = 0
            
            error_detail = f"録画ファイルが見つかりませんでした（ミーティングID: {meeting_id}）。\n\n"
            error_detail += "【確認事項】\n"
            error_detail += f"1. ローカル録画ファイルが保存されているか確認してください\n"
            error_detail += f"   録画保存先ディレクトリ: {recording_dir_str}\n"
            error_detail += f"2. Zoomクラウドに録画が保存されているか確認してください\n"
            error_detail += f"3. 録画が完了しているか確認してください\n"
            error_detail += f"4. 録画ファイルの形式が正しいか確認してください（MP4、MOV、M4A、MP3）\n"
            error_detail += f"5. 録画ファイルのサイズが1MB以上であることを確認してください\n"
            if recordings_count > 0:
                error_detail += f"6. 見つかったローカル録画ファイル数: {recordings_count}件（ミーティングIDに一致するものは見つかりませんでした）\n"
            else:
                error_detail += f"6. ローカル録画ファイルが見つかりませんでした（録画保存先ディレクトリを確認してください）\n"
            error_detail += "\n【デバッグ情報】\n"
            error_detail += f"- ミーティングIDの型: {type(meeting_id).__name__}\n"
            error_detail += f"- ミーティングIDの値: {meeting_id}\n"
            error_detail += f"- 録画保存先ディレクトリ: {recording_dir_str}\n"
            error_detail += f"- 見つかったローカル録画ファイル数: {recordings_count}件\n"
            error_detail += f"- ローカル録画: 見つかりませんでした\n"
            error_detail += f"- Zoom API録画: 取得を試みましたが、見つかりませんでした"
            raise Exception(error_detail)
        
        # ========== ステップ2: Gemini APIで議事録を生成 ==========
        
        gemini_client = GeminiClient(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model_name
        )
        
        # 文字起こしがあればそれを使用、なければ動画から生成
        if transcript_text:
            logger.info(f"[タスク {task_id}] Gemini APIで文字起こしから議事録を生成")
            processing_tasks[task_id]["progress"] = 50
            processing_tasks[task_id]["message"] = "Gemini APIで文字起こしから議事録を生成中..."
            
            # 文字起こしから議事録を生成（同期的な処理を実行スレッドで実行）
            with concurrent.futures.ThreadPoolExecutor() as executor:
                transcript = await loop.run_in_executor(
                    executor,
                    gemini_client.summarize_transcript,
                    transcript_text
                )
        else:
            logger.info(f"[タスク {task_id}] 動画ファイルから議事録を生成")
            processing_tasks[task_id]["progress"] = 50
            processing_tasks[task_id]["message"] = "Gemini APIで録画内容を解析中..."
        
        # ファイル拡張子で動画か音声かを判定
        file_ext = Path(recording_file_path).suffix.lower()
        logger.info(f"[タスク {task_id}] ファイル形式: {file_ext}")
        
        # .zoomファイルはZoomの独自形式で、Gemini APIが直接処理できない可能性があります
        if file_ext == ".zoom":
            error_msg = f".zoomファイルはZoomの独自形式で、Gemini APIが直接処理できません。\n\n"
            error_msg += f"【対処方法】\n"
            error_msg += f"1. Zoomアプリで.zoomファイルをダブルクリックしてMP4に変換してください\n"
            error_msg += f"2. 変換後、MP4ファイルが同じディレクトリに保存されます\n"
            error_msg += f"3. 再度議事録生成を実行してください\n\n"
            error_msg += f"【ファイル情報】\n"
            error_msg += f"- ファイルパス: {recording_file_path}\n"
            error_msg += f"- ファイル形式: .zoom（変換が必要）"
            raise Exception(error_msg)
        
        # Gemini APIで録画ファイルから議事録を生成（同期的な処理を実行スレッドで実行）
        with concurrent.futures.ThreadPoolExecutor() as executor:
            if file_ext in [".mp4", ".mov", ".avi", ".mkv"]:
                logger.info(f"[タスク {task_id}] 動画ファイルとして処理")
                transcript = await loop.run_in_executor(
                    executor,
                    gemini_client.transcribe_and_summarize,
                    recording_file_path
                )
            elif file_ext in [".mp3", ".wav", ".m4a", ".ogg"]:
                logger.info(f"[タスク {task_id}] 音声ファイルとして処理")
                transcript = await loop.run_in_executor(
                    executor,
                    gemini_client.transcribe_audio,
                    recording_file_path
                )
            else:
                logger.info(f"[タスク {task_id}] デフォルト（動画）として処理")
                transcript = await loop.run_in_executor(
                    executor,
                    gemini_client.transcribe_and_summarize,
                    recording_file_path
                )
        
        if not transcript or len(transcript.strip()) == 0:
            raise Exception("議事録の生成に失敗しました。Gemini APIのレスポンスが空です。")
        
        logger.info(f"[タスク {task_id}] 議事録を生成しました（{len(transcript)}文字）")
        processing_tasks[task_id]["progress"] = 80
        processing_tasks[task_id]["message"] = "議事録の生成が完了しました"
        
        # ========== ステップ3: Chatwork APIで議事録を送信 ==========
        logger.info(f"[タスク {task_id}] Chatworkに送信開始: ルームID={room_id}")
        processing_tasks[task_id]["progress"] = 90
        processing_tasks[task_id]["message"] = "Chatworkに送信中..."
        
        chatwork_client = ChatworkClient(api_token=settings.chatwork_api_token)
        
        # メッセージをフォーマット
        message = f"""[info][title]Zoom会議議事録[/title]
ミーティングID: {meeting_id}

{transcript}
[/info]"""
        
        # Chatworkに送信（同期的な処理を実行スレッドで実行）
        with concurrent.futures.ThreadPoolExecutor() as executor:
            await loop.run_in_executor(
                executor,
                chatwork_client.send_message,
                room_id,
                message
            )
        
        logger.info(f"[タスク {task_id}] Chatworkへの送信が完了しました")
        
        # 手動処理時に処理済みマークを付ける（重複防止）
        try:
            from scheduler import AutoProcessConfig
            config = AutoProcessConfig()
            config.mark_as_processed(meeting_id)
            logger.info(f"[タスク {task_id}] 処理済みマークを付けました: ミーティングID={meeting_id}")
        except Exception as mark_error:
            logger.warning(f"[タスク {task_id}] 処理済みマークの付与に失敗: {mark_error}")
        
        processing_tasks[task_id]["progress"] = 100
        processing_tasks[task_id]["status"] = "completed"
        processing_tasks[task_id]["message"] = "処理が完了しました！議事録をChatworkに送信しました。"
        processing_tasks[task_id]["result"] = {
            "success": True,
            "transcript": transcript,
            "meeting_id": meeting_id,
            "room_id": room_id,
            "file_path": recording_file_path
        }
        
        return processing_tasks[task_id]["result"]
        
    except Exception as e:
        logger.error(f"[タスク {task_id}] エラーが発生しました: {e}", exc_info=True)
        processing_tasks[task_id]["status"] = "error"
        processing_tasks[task_id]["message"] = f"エラー: {str(e)}"
        processing_tasks[task_id]["result"] = {
            "success": False,
            "error": str(e),
            "meeting_id": meeting_id,
            "room_id": room_id
        }
        
        # エラー時も一時ファイルを削除
        try:
            if recording_file_path and os.path.exists(recording_file_path):
                os.remove(recording_file_path)
                logger.info(f"[タスク {task_id}] 一時ファイルを削除しました: {recording_file_path}")
        except Exception as cleanup_error:
            logger.warning(f"[タスク {task_id}] 一時ファイルの削除に失敗: {cleanup_error}")
        
        return processing_tasks[task_id]["result"]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """メインページ"""
    global settings
    # 設定が読み込まれていない場合は読み込む
    if settings is None:
        reload_settings()
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/settings/save")
async def save_api_settings(
    zoom_api_key: Optional[str] = Form(None),
    zoom_api_secret: Optional[str] = Form(None),
    zoom_account_id: Optional[str] = Form(None),
    gemini_api_key: Optional[str] = Form(None),
    gemini_model_name: Optional[str] = Form(None),
    chatwork_api_token: Optional[str] = Form(None),
    default_chatwork_room_id: Optional[str] = Form(None)
):
    """
    API設定を保存
    Geminiモデル名は指定されない場合はデフォルト値を使用
    フォームから送信された値が空の場合は、既存の値を保持する
    """
    global settings
    # 設定が読み込まれていない場合は読み込む
    if settings is None:
        reload_settings()
    
    import os
    from pathlib import Path
    
    try:
        env_file = Path(".env")
        env_lines = []
        existing_settings = {}
        
        # 既存の.envファイルを読み込む
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                env_lines = f.readlines()
            
            # 既存の設定値を読み込む
            for line in env_lines:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key_value = line.split("=", 1)
                    if len(key_value) == 2:
                        key = key_value[0].strip()
                        value = key_value[1].strip()
                        existing_settings[key] = value
        
        # 設定値を辞書に格納（空白を除去）
        # フォームから送信された値が空の場合は、既存の値を保持
        new_settings = {}
        
        # Zoom API設定
        if zoom_api_key and zoom_api_key.strip():
            new_settings["ZOOM_API_KEY"] = zoom_api_key.strip()
        elif "ZOOM_API_KEY" in existing_settings:
            new_settings["ZOOM_API_KEY"] = existing_settings["ZOOM_API_KEY"]
        
        if zoom_api_secret and zoom_api_secret.strip():
            new_settings["ZOOM_API_SECRET"] = zoom_api_secret.strip()
        elif "ZOOM_API_SECRET" in existing_settings:
            new_settings["ZOOM_API_SECRET"] = existing_settings["ZOOM_API_SECRET"]
        
        if zoom_account_id and zoom_account_id.strip():
            new_settings["ZOOM_ACCOUNT_ID"] = zoom_account_id.strip()
        elif "ZOOM_ACCOUNT_ID" in existing_settings:
            new_settings["ZOOM_ACCOUNT_ID"] = existing_settings["ZOOM_ACCOUNT_ID"]
        
        # Gemini API設定
        if gemini_api_key and gemini_api_key.strip():
            new_settings["GEMINI_API_KEY"] = gemini_api_key.strip()
            logger.debug(f"Gemini API Keyを更新: {gemini_api_key[:5]}...{gemini_api_key[-5:] if len(gemini_api_key) > 10 else '***'}")
        elif "GEMINI_API_KEY" in existing_settings:
            new_settings["GEMINI_API_KEY"] = existing_settings["GEMINI_API_KEY"]
            logger.debug(f"Gemini API Keyを保持: {existing_settings['GEMINI_API_KEY'][:5]}...{existing_settings['GEMINI_API_KEY'][-5:] if len(existing_settings['GEMINI_API_KEY']) > 10 else '***'}")
        
        # Geminiモデル名は指定されない場合はデフォルト値（gemini-2.5-pro）を使用
        if gemini_model_name and gemini_model_name.strip():
            new_settings["GEMINI_MODEL_NAME"] = gemini_model_name.strip()
        elif "GEMINI_MODEL_NAME" in existing_settings:
            new_settings["GEMINI_MODEL_NAME"] = existing_settings["GEMINI_MODEL_NAME"]
        else:
            # 既存の設定がない場合のみデフォルト値を設定
            new_settings["GEMINI_MODEL_NAME"] = "gemini-2.5-pro"
        
        # Chatwork API設定
        if chatwork_api_token and chatwork_api_token.strip():
            new_settings["CHATWORK_API_TOKEN"] = chatwork_api_token.strip()
            logger.debug(f"Chatwork API Tokenを更新: {chatwork_api_token[:5]}...{chatwork_api_token[-5:] if len(chatwork_api_token) > 10 else '***'}")
        elif "CHATWORK_API_TOKEN" in existing_settings:
            new_settings["CHATWORK_API_TOKEN"] = existing_settings["CHATWORK_API_TOKEN"]
            logger.debug(f"Chatwork API Tokenを保持: {existing_settings['CHATWORK_API_TOKEN'][:5]}...{existing_settings['CHATWORK_API_TOKEN'][-5:] if len(existing_settings['CHATWORK_API_TOKEN']) > 10 else '***'}")
        
        if default_chatwork_room_id and default_chatwork_room_id.strip():
            new_settings["DEFAULT_CHATWORK_ROOM_ID"] = default_chatwork_room_id.strip()
        elif "DEFAULT_CHATWORK_ROOM_ID" in existing_settings:
            new_settings["DEFAULT_CHATWORK_ROOM_ID"] = existing_settings["DEFAULT_CHATWORK_ROOM_ID"]
        
        # 既存の設定を更新または追加
        existing_keys = set()
        new_lines = []
        updated_keys = []
        
        for line in env_lines:
            original_line = line
            line = line.rstrip()  # 右側の改行のみ削除（左側の空白は保持）
            
            if not line.strip() or line.strip().startswith("#"):
                new_lines.append(original_line if original_line.endswith("\n") else original_line + "\n")
                continue
            
            key_value = line.split("=", 1)
            if len(key_value) == 2:
                key = key_value[0].strip()
                existing_keys.add(key)
                
                # 更新する設定がある場合は更新
                if key in new_settings:
                    new_lines.append(f"{key}={new_settings[key]}\n")
                    updated_keys.append(key)
                    del new_settings[key]
                else:
                    # 既存の設定を保持（new_settingsに含まれていない場合）
                    # ただし、new_settingsに含まれている場合は既に処理済み
                    new_lines.append(original_line if original_line.endswith("\n") else original_line + "\n")
            else:
                # パースできない行はそのまま保持
                new_lines.append(original_line if original_line.endswith("\n") else original_line + "\n")
        
        # 新しい設定を追加（既存の設定にないもの）
        for key, value in new_settings.items():
            new_lines.append(f"{key}={value}\n")
            updated_keys.append(key)
        
        logger.debug(f"更新された設定キー: {updated_keys}")
        
        # .envファイルに書き込む
        with open(env_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        
        # 保存する設定の詳細をログに記録（デバッグ用）
        logger.info(f"設定を保存しました: {list(new_settings.keys())}")
        logger.info(f"保存する設定値:")
        for key, value in new_settings.items():
            if "KEY" in key or "SECRET" in key or "TOKEN" in key:
                logger.info(f"  {key}: {value[:5]}...{value[-5:] if len(value) > 10 else '***'} (長さ: {len(value)})")
            else:
                logger.info(f"  {key}: {value}")
        
        # 既存の設定を保持したものもログに記録
        kept_settings = []
        for key in ["ZOOM_API_KEY", "ZOOM_API_SECRET", "ZOOM_ACCOUNT_ID", "GEMINI_API_KEY", "CHATWORK_API_TOKEN"]:
            if key not in new_settings and key in existing_settings:
                kept_settings.append(key)
        if kept_settings:
            logger.info(f"既存の設定を保持しました: {kept_settings}")
        
        # 設定を再読み込み
        reload_settings()
        
        # 再読み込み後の設定値をログに記録（デバッグ用）
        if settings:
            logger.info(f"再読み込み後の設定確認:")
            logger.info(f"  ZOOM_API_KEY: {settings.zoom_api_key[:10] if settings.zoom_api_key else 'None'}... (長さ: {len(settings.zoom_api_key) if settings.zoom_api_key else 0})")
            logger.info(f"  ZOOM_API_SECRET: {settings.zoom_api_secret[:10] if settings.zoom_api_secret else 'None'}... (長さ: {len(settings.zoom_api_secret) if settings.zoom_api_secret else 0})")
            logger.info(f"  ZOOM_ACCOUNT_ID: {settings.zoom_account_id if settings.zoom_account_id else 'None'}")
            logger.info(f"  GEMINI_API_KEY: {settings.gemini_api_key[:10] if settings.gemini_api_key else 'None'}... (長さ: {len(settings.gemini_api_key) if settings.gemini_api_key else 0})")
            logger.info(f"  CHATWORK_API_TOKEN: {settings.chatwork_api_token[:10] if settings.chatwork_api_token else 'None'}... (長さ: {len(settings.chatwork_api_token) if settings.chatwork_api_token else 0})")
        
        return JSONResponse({
            "success": True,
            "message": "設定を保存しました"
        })
        
    except Exception as e:
        logger.error(f"設定の保存に失敗: {e}", exc_info=True)
        return JSONResponse({
            "success": False,
            "message": f"設定の保存に失敗しました: {str(e)}"
        }, status_code=500)


@app.get("/api/settings/load")
async def load_api_settings():
    """
    API設定を読み込む（値はマスクして返す）
    """
    try:
        if not settings:
            return JSONResponse({
                "success": False,
                "message": "設定が読み込まれていません"
            })
        
        return JSONResponse({
            "success": True,
            "settings": {
                "zoom_api_key": "***" if hasattr(settings, 'zoom_api_key') and settings.zoom_api_key else "",
                "zoom_api_secret": "***" if hasattr(settings, 'zoom_api_secret') and settings.zoom_api_secret else "",
                "zoom_account_id": settings.zoom_account_id if hasattr(settings, 'zoom_account_id') else "",
                "gemini_api_key": "***" if hasattr(settings, 'gemini_api_key') and settings.gemini_api_key else "",
                "gemini_model_name": settings.gemini_model_name if hasattr(settings, 'gemini_model_name') else "",
                "chatwork_api_token": "***" if hasattr(settings, 'chatwork_api_token') and settings.chatwork_api_token else "",
                "default_chatwork_room_id": settings.default_chatwork_room_id if hasattr(settings, 'default_chatwork_room_id') else ""
            }
        })
    except Exception as e:
        logger.error(f"設定の読み込みに失敗: {e}", exc_info=True)
        return JSONResponse({
            "success": False,
            "message": f"設定の読み込みに失敗しました: {str(e)}"
        }, status_code=500)


@app.post("/api/process")
async def process_meeting(
    meeting_id: str = Form(...),
    room_id: str = Form(...)
):
    """
    議事録生成処理を開始
    
    Args:
        meeting_id: ZoomミーティングID
        room_id: ChatworkルームID
    """
    global settings
    # 設定が読み込まれていない場合は読み込む
    if settings is None:
        reload_settings()
    # ミーティングIDとルームIDの検証
    meeting_id = meeting_id.strip()
    room_id = room_id.strip()
    
    if not meeting_id:
        return JSONResponse({
            "success": False,
            "message": "ミーティングIDが入力されていません"
        }, status_code=400)
    
    if not room_id:
        return JSONResponse({
            "success": False,
            "message": "ChatworkルームIDが入力されていません"
        }, status_code=400)
    
    # ログに記録
    logger.info(f"議事録生成処理を開始: ミーティングID={meeting_id} (型: {type(meeting_id).__name__}), ルームID={room_id}")
    
    task_id = str(uuid.uuid4())
    
    # 非同期タスクを開始
    asyncio.create_task(
        process_meeting_recording_task(task_id, meeting_id, room_id)
    )
    
    return JSONResponse({
        "task_id": task_id,
        "status": "started",
        "meeting_id": meeting_id,
        "room_id": room_id
    })


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """
    処理状況を取得
    
    Args:
        task_id: タスクID
        
    Returns:
        処理状況
    """
    if task_id not in processing_tasks:
        # タスクが見つからない場合、デフォルト値を返す（処理中として扱う）
        logger.warning(f"タスク {task_id} が見つかりません。デフォルト値を返します。")
        return JSONResponse({
            "status": "processing",
            "progress": 0,
            "message": "処理を開始しています..."
        })
    
    return JSONResponse(processing_tasks[task_id])


@app.get("/api/test/zoom")
async def test_zoom(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    account_id: Optional[str] = None
):
    """
    Zoom API接続テスト
    フォームから送信された値があればそれを使用、なければ現在の設定を使用
    """
    global settings
    # 設定が読み込まれていない場合は読み込む
    if settings is None:
        reload_settings()
    
    # フォームから送信された値があればそれを使用、なければ現在の設定を使用
    form_api_key = api_key.strip() if api_key and api_key.strip() else None
    form_api_secret = api_secret.strip() if api_secret and api_secret.strip() else None
    form_account_id = account_id.strip() if account_id and account_id.strip() else None
    
    settings_api_key = settings.zoom_api_key.strip() if settings and settings.zoom_api_key and settings.zoom_api_key.strip() else None
    settings_api_secret = settings.zoom_api_secret.strip() if settings and settings.zoom_api_secret and settings.zoom_api_secret.strip() else None
    settings_account_id = settings.zoom_account_id.strip() if settings and settings.zoom_account_id and settings.zoom_account_id.strip() else None
    
    # 使用する値を決定（フォームの値があればそれを使用、なければ設定から取得）
    zoom_api_key = form_api_key or settings_api_key
    zoom_api_secret = form_api_secret or settings_api_secret
    zoom_account_id = form_account_id or settings_account_id
    
    # どの値が使用されているかをログに記録
    if form_api_key:
        logger.info(f"接続テスト: フォームから送信された値を使用")
        logger.info(f"  API Key: {form_api_key[:5]}...{form_api_key[-5:] if len(form_api_key) > 10 else ''} (長さ: {len(form_api_key)})")
        logger.info(f"  API Secret: {form_api_secret[:5] if form_api_secret else 'None'}...{form_api_secret[-5:] if form_api_secret and len(form_api_secret) > 10 else ''} (長さ: {len(form_api_secret) if form_api_secret else 0})")
        logger.info(f"  Account ID: {form_account_id}")
    elif settings_api_key:
        logger.info(f"接続テスト: 設定から読み込んだ値を使用")
        logger.info(f"  API Key: {settings_api_key[:5]}...{settings_api_key[-5:] if len(settings_api_key) > 10 else ''} (長さ: {len(settings_api_key)})")
        logger.info(f"  API Secret: {settings_api_secret[:5] if settings_api_secret else 'None'}...{settings_api_secret[-5:] if settings_api_secret and len(settings_api_secret) > 10 else ''} (長さ: {len(settings_api_secret) if settings_api_secret else 0})")
        logger.info(f"  Account ID: {settings_account_id}")
    
    # 設定値の検証
    if not zoom_api_key:
        return JSONResponse({
            "success": False,
            "message": "ZOOM_API_KEYが設定されていません。API設定を確認してください。"
        }, status_code=400)
    
    if not zoom_api_secret:
        return JSONResponse({
            "success": False,
            "message": "ZOOM_API_SECRETが設定されていません。API設定を確認してください。"
        }, status_code=400)
    
    try:
        # 以前動作していた方法: まずJWT認証を試す（Account IDが設定されていても）
        # 以前はAccount IDが設定されていなかったため、JWT認証で動作していた可能性が高い
        zoom_client_jwt = ZoomClient(
            api_key=zoom_api_key,
            api_secret=zoom_api_secret,
            account_id=None  # JWT認証を使用
        )
        
        # まずJWT認証を試す（以前動作していた方法）
        # JWT認証ではOAuthトークンエンドポイントにアクセスしない
        try:
            logger.info("JWT認証を試します（以前動作していた方法）")
            # JWTトークンを直接生成（OAuthトークンエンドポイントにはアクセスしない）
            token = zoom_client_jwt._generate_jwt_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            response = requests.get(f"{zoom_client_jwt.BASE_URL}/users/me", headers=headers)
            
            if response.status_code == 200:
                user_info = response.json()
                return JSONResponse({
                    "success": True,
                    "message": f"Zoom API接続成功（JWT認証、ユーザー: {user_info.get('email', 'N/A')}）"
                })
            elif response.status_code == 401:
                # JWT認証が失敗した場合、Server-to-Server OAuthを試す
                logger.warning(f"JWT認証が失敗しました（{response.status_code}）。Server-to-Server OAuthを試します")
                if zoom_account_id:
                    try:
                        zoom_client = ZoomClient(
                            api_key=zoom_api_key,
                            api_secret=zoom_api_secret,
                            account_id=zoom_account_id
                        )
                        # OAuth認証を使用（force_oauth=True）
                        headers = zoom_client._get_headers(force_oauth=True)
                        response = requests.get(f"{zoom_client.BASE_URL}/users/me", headers=headers)
                        
                        # Server-to-Server OAuthのレスポンスを処理
                        if response.status_code == 200:
                            user_info = response.json()
                            return JSONResponse({
                                "success": True,
                                "message": f"Zoom API接続成功（Server-to-Server OAuth、ユーザー: {user_info.get('email', 'N/A')}）"
                            })
                        else:
                            error_data = response.json()
                            error_code = error_data.get('code', '')
                            error_message = error_data.get('message', 'Unknown error')
                            
                            # 使用されている値の情報を追加
                            used_value_info = ""
                            if form_api_key:
                                used_value_info = f"\n【使用された値】\n" \
                                                f"フォームから送信された値を使用: API Key={form_api_key[:5]}...{form_api_key[-5:] if len(form_api_key) > 10 else ''}\n" \
                                                f"設定ファイルの値: API Key={settings_api_key[:5] if settings_api_key else 'N/A'}...{settings_api_key[-5:] if settings_api_key and len(settings_api_key) > 10 else ''}\n" \
                                                f"⚠️ フォームの値が間違っている可能性があります。フォームをクリアして、設定ファイルの値を使用してください。\n"
                            elif settings_api_key:
                                used_value_info = f"\n【使用された値】\n" \
                                                f"設定ファイルから読み込んだ値を使用: API Key={settings_api_key[:5]}...{settings_api_key[-5:] if len(settings_api_key) > 10 else ''}\n"
                            
                            return JSONResponse({
                                "success": False,
                                "message": f"Zoom API接続失敗（Server-to-Server OAuth）: {error_code} - {error_message}{used_value_info}\n"
                                         f"【確認事項】\n"
                                         f"1. Zoom Marketplaceでアプリが「Activated」状態になっているか確認してください\n"
                                         f"2. アプリタイプが「Server-to-Server OAuth」になっているか確認してください\n"
                                         f"3. 必要なスコープが有効になっているか確認してください\n"
                                         f"4. フォームに古い値が残っていないか確認してください（フォームをクリアして再試行）"
                            }, status_code=response.status_code)
                    except Exception as oauth_error:
                        # JWT認証とOAuthの両方が失敗
                        jwt_error_data = response.json() if response.status_code == 401 else {}
                        jwt_error_code = jwt_error_data.get('code', '')
                        jwt_error_message = jwt_error_data.get('message', 'Unknown error')
                        
                        # 使用されている値の情報を追加
                        used_value_info = ""
                        if form_api_key:
                            used_value_info = f"\n【使用された値】\n" \
                                            f"フォームから送信された値を使用: API Key={form_api_key[:5]}...{form_api_key[-5:] if len(form_api_key) > 10 else ''}\n" \
                                            f"設定ファイルの値: API Key={settings_api_key[:5] if settings_api_key else 'N/A'}...{settings_api_key[-5:] if settings_api_key and len(settings_api_key) > 10 else ''}\n" \
                                            f"⚠️ フォームの値が間違っている可能性があります。フォームをクリアして、設定ファイルの値を使用してください。\n"
                        elif settings_api_key:
                            used_value_info = f"\n【使用された値】\n" \
                                            f"設定ファイルから読み込んだ値を使用: API Key={settings_api_key[:5]}...{settings_api_key[-5:] if len(settings_api_key) > 10 else ''}\n"
                        
                        return JSONResponse({
                            "success": False,
                            "message": f"Zoom API接続失敗: JWT認証とServer-to-Server OAuthの両方が失敗しました。\n\n"
                                     f"JWT認証エラー: {jwt_error_code} - {jwt_error_message}\n"
                                     f"Server-to-Server OAuthエラー: {str(oauth_error)}{used_value_info}\n"
                                     f"【確認事項】\n"
                                     f"1. Zoom Marketplaceでアプリが「Activated」状態になっているか確認してください\n"
                                     f"2. アプリタイプが「JWT」または「Server-to-Server OAuth」のいずれかが正しく設定されているか確認してください\n"
                                     f"3. API KeyとAPI Secretが正しいアプリタイプのものか確認してください\n"
                                     f"4. 必要なスコープが有効になっているか確認してください\n"
                                     f"5. フォームに古い値が残っていないか確認してください（フォームをクリアして再試行）"
        }, status_code=500)
                else:
                    # Account IDが設定されていない場合
                    error_data = response.json()
                    error_code = error_data.get('code', '')
                    error_message = error_data.get('message', 'Unknown error')
                    
                    # 使用されている値の情報を追加
                    used_value_info = ""
                    if form_api_key:
                        used_value_info = f"\n【使用された値】\n" \
                                        f"フォームから送信された値を使用: API Key={form_api_key[:5]}...{form_api_key[-5:] if len(form_api_key) > 10 else ''}\n" \
                                        f"設定ファイルの値: API Key={settings_api_key[:5] if settings_api_key else 'N/A'}...{settings_api_key[-5:] if settings_api_key and len(settings_api_key) > 10 else ''}\n" \
                                        f"⚠️ フォームの値が間違っている可能性があります。フォームをクリアして、設定ファイルの値を使用してください。\n"
                    elif settings_api_key:
                        used_value_info = f"\n【使用された値】\n" \
                                        f"設定ファイルから読み込んだ値を使用: API Key={settings_api_key[:5]}...{settings_api_key[-5:] if len(settings_api_key) > 10 else ''}\n"
                    
                    return JSONResponse({
                        "success": False,
                        "message": f"Zoom API接続失敗（JWT認証）: {error_code} - {error_message}{used_value_info}\n"
                                 f"【確認事項】\n"
                                 f"1. Zoom Marketplaceで「JWT」タイプのアプリが作成されているか確認してください\n"
                                 f"2. アプリが「Activated」状態になっているか確認してください\n"
                                 f"3. API KeyとAPI SecretがJWT認証用のものか確認してください\n"
                                 f"4. 必要なスコープが有効になっているか確認してください\n"
                                 f"5. フォームに古い値が残っていないか確認してください（フォームをクリアして再試行）"
                    }, status_code=response.status_code)
            else:
                # その他のエラー
                error_data = response.json()
                error_code = error_data.get('code', '')
                error_message = error_data.get('message', 'Unknown error')
                
                # 使用されている値の情報を追加
                used_value_info = ""
                if form_api_key:
                    used_value_info = f"\n【使用された値】\n" \
                                    f"フォームから送信された値を使用: API Key={form_api_key[:5]}...{form_api_key[-5:] if len(form_api_key) > 10 else ''}\n" \
                                    f"設定ファイルの値: API Key={settings_api_key[:5] if settings_api_key else 'N/A'}...{settings_api_key[-5:] if settings_api_key and len(settings_api_key) > 10 else ''}\n" \
                                    f"⚠️ フォームの値が間違っている可能性があります。フォームをクリアして、設定ファイルの値を使用してください。\n"
                elif settings_api_key:
                    used_value_info = f"\n【使用された値】\n" \
                                    f"設定ファイルから読み込んだ値を使用: API Key={settings_api_key[:5]}...{settings_api_key[-5:] if len(settings_api_key) > 10 else ''}\n"
                
                return JSONResponse({
                    "success": False,
                    "message": f"Zoom API接続失敗（JWT認証）: {error_code} - {error_message}{used_value_info}\n"
                             f"【確認事項】\n"
                             f"1. Zoom Marketplaceで「JWT」タイプのアプリが作成されているか確認してください\n"
                             f"2. アプリが「Activated」状態になっているか確認してください\n"
                             f"3. API KeyとAPI SecretがJWT認証用のものか確認してください\n"
                             f"4. 必要なスコープが有効になっているか確認してください\n"
                             f"5. フォームに古い値が残っていないか確認してください（フォームをクリアして再試行）"
                }, status_code=response.status_code)
        except requests.exceptions.HTTPError as jwt_error:
            # JWT認証がHTTPエラーで失敗した場合
            logger.warning(f"JWT認証がHTTPエラーで失敗しました: {jwt_error}")
            # Server-to-Server OAuthを試す
            if zoom_account_id:
                try:
                    zoom_client = ZoomClient(
                        api_key=zoom_api_key,
                        api_secret=zoom_api_secret,
                        account_id=zoom_account_id
                    )
                    # OAuth認証を使用（force_oauth=True）
                    headers = zoom_client._get_headers(force_oauth=True)
                    response = requests.get(f"{zoom_client.BASE_URL}/users/me", headers=headers)
                    
                    if response.status_code == 200:
                        user_info = response.json()
                        return JSONResponse({
                            "success": True,
                            "message": f"Zoom API接続成功（Server-to-Server OAuth、ユーザー: {user_info.get('email', 'N/A')}）"
                        })
                    else:
                        error_data = response.json()
                        error_code = error_data.get('code', '')
                        error_message = error_data.get('message', 'Unknown error')
                        return JSONResponse({
                            "success": False,
                            "message": f"Zoom API接続失敗（Server-to-Server OAuth）: {error_code} - {error_message}"
                        }, status_code=response.status_code)
                except Exception as oauth_error:
                    logger.warning(f"Server-to-Server OAuth認証が失敗しました: {oauth_error}")
                    return JSONResponse({
                        "success": False,
                        "message": f"Zoom API接続失敗: JWT認証とServer-to-Server OAuthの両方が失敗しました。\n\n"
                                 f"JWTエラー: {str(jwt_error)}\n"
                                 f"OAuthエラー: {str(oauth_error)}\n\n"
                                 f"【確認事項】\n"
                                 f"1. Zoom Marketplaceでアプリが「Activated」状態になっているか確認してください\n"
                                 f"2. アプリタイプが正しく設定されているか確認してください\n"
                                 f"3. 必要なスコープが有効になっているか確認してください"
                    }, status_code=500)
            else:
                return JSONResponse({
                    "success": False,
                    "message": f"Zoom API接続失敗（JWT認証）: {str(jwt_error)}\n\n"
                             f"【確認事項】\n"
                             f"1. Zoom Marketplaceで「JWT」タイプのアプリが作成されているか確認してください\n"
                             f"2. アプリが「Activated」状態になっているか確認してください\n"
                             f"3. API KeyとAPI SecretがJWT認証用のものか確認してください"
                }, status_code=500)
        except Exception as jwt_error:
            # JWT認証がその他の例外で失敗した場合
            logger.warning(f"JWT認証が例外で失敗しました: {jwt_error}")
            # Server-to-Server OAuthを試す
            if zoom_account_id:
                try:
                    zoom_client = ZoomClient(
                        api_key=zoom_api_key,
                        api_secret=zoom_api_secret,
                        account_id=zoom_account_id
                    )
                    # OAuth認証を使用（force_oauth=True）
                    headers = zoom_client._get_headers(force_oauth=True)
                    response = requests.get(f"{zoom_client.BASE_URL}/users/me", headers=headers)
                    
                    if response.status_code == 200:
                        user_info = response.json()
                        return JSONResponse({
                            "success": True,
                            "message": f"Zoom API接続成功（Server-to-Server OAuth、ユーザー: {user_info.get('email', 'N/A')}）"
                        })
                    else:
                        error_data = response.json()
                        error_code = error_data.get('code', '')
                        error_message = error_data.get('message', 'Unknown error')
                        return JSONResponse({
                            "success": False,
                            "message": f"Zoom API接続失敗（Server-to-Server OAuth）: {error_code} - {error_message}"
                        }, status_code=response.status_code)
                except Exception as oauth_error:
                    return JSONResponse({
                        "success": False,
                        "message": f"Zoom API接続失敗: JWT認証とServer-to-Server OAuthの両方が失敗しました。\n\n"
                                 f"JWTエラー: {str(jwt_error)}\n"
                                 f"OAuthエラー: {str(oauth_error)}\n\n"
                                 f"【確認事項】\n"
                                 f"1. Zoom Marketplaceでアプリが「Activated」状態になっているか確認してください\n"
                                 f"2. アプリタイプが正しく設定されているか確認してください\n"
                                 f"3. 必要なスコープが有効になっているか確認してください"
                    }, status_code=500)
            else:
                return JSONResponse({
                    "success": False,
                    "message": f"Zoom API接続失敗（JWT認証）: {str(jwt_error)}\n\n"
                             f"【確認事項】\n"
                             f"1. Zoom Marketplaceで「JWT」タイプのアプリが作成されているか確認してください\n"
                             f"2. アプリが「Activated」状態になっているか確認してください\n"
                             f"3. API KeyとAPI SecretがJWT認証用のものか確認してください"
                }, status_code=500)
    except requests.exceptions.HTTPError as e:
        error_msg = str(e)
        # エラーメッセージに詳細情報が含まれている場合はそのまま使用
        if "【確認事項】" in error_msg:
            # エラーメッセージに改行が含まれている場合はそのまま返す
            return JSONResponse({
                "success": False,
                "message": error_msg.replace('\n', '<br>')  # HTML表示用に改行を変換
            }, status_code=e.response.status_code if e.response else 500)
        
        if e.response is not None:
            try:
                error_data = e.response.json()
                error_msg = error_data.get('message', error_data.get('reason', error_data.get('error_description', error_msg)))
            except:
                error_msg = e.response.text[:200] if e.response.text else error_msg
        
        # 使用されている値の情報を追加
        used_value_info = ""
        if form_api_key:
            used_value_info = f"\n【使用された値】\n" \
                            f"フォームから送信された値を使用: API Key={form_api_key[:5]}...{form_api_key[-5:] if len(form_api_key) > 10 else ''}\n" \
                            f"設定ファイルの値: API Key={settings_api_key[:5] if settings_api_key else 'N/A'}...{settings_api_key[-5:] if settings_api_key and len(settings_api_key) > 10 else ''}\n" \
                            f"⚠️ フォームの値が間違っている可能性があります。フォームをクリアして、設定ファイルの値を使用してください。\n"
        elif settings_api_key:
            used_value_info = f"\n【使用された値】\n" \
                            f"設定ファイルから読み込んだ値を使用: API Key={settings_api_key[:5]}...{settings_api_key[-5:] if len(settings_api_key) > 10 else ''}\n"
        
        return JSONResponse({
            "success": False,
            "message": f"Zoom API接続失敗: {error_msg}{used_value_info}\n"
                     f"【確認事項】\n"
                     f"1. Zoom Marketplaceでアプリが「Activated」状態になっているか確認してください\n"
                     f"2. アプリタイプが正しく設定されているか確認してください\n"
                     f"3. 必要なスコープが有効になっているか確認してください\n"
                     f"4. フォームに古い値が残っていないか確認してください（フォームをクリアして再試行）"
        }, status_code=e.response.status_code if e.response else 500)
    except ValueError as e:
        # 設定値の検証エラー
        return JSONResponse({
            "success": False,
            "message": f"設定エラー: {str(e)}"
        }, status_code=400)
    except Exception as e:
        # 使用されている値の情報を追加（変数が定義されている場合のみ）
        used_value_info = ""
        try:
            if 'form_api_key' in locals() and form_api_key:
                used_value_info = f"\n【使用された値】\n" \
                                f"フォームから送信された値を使用: API Key={form_api_key[:5]}...{form_api_key[-5:] if len(form_api_key) > 10 else ''}\n" \
                                f"設定ファイルの値: API Key={settings_api_key[:5] if 'settings_api_key' in locals() and settings_api_key else 'N/A'}...{settings_api_key[-5:] if 'settings_api_key' in locals() and settings_api_key and len(settings_api_key) > 10 else ''}\n" \
                                f"⚠️ フォームの値が間違っている可能性があります。フォームをクリアして、設定ファイルの値を使用してください。\n"
            elif 'settings_api_key' in locals() and settings_api_key:
                used_value_info = f"\n【使用された値】\n" \
                                f"設定ファイルから読み込んだ値を使用: API Key={settings_api_key[:5]}...{settings_api_key[-5:] if len(settings_api_key) > 10 else ''}\n"
        except:
            pass  # 変数が定義されていない場合は無視
        
        return JSONResponse({
            "success": False,
            "message": f"Zoom API接続失敗: {str(e)}{used_value_info}\n"
                     f"【確認事項】\n"
                     f"1. Zoom Marketplaceでアプリが「Activated」状態になっているか確認してください\n"
                     f"2. アプリタイプが正しく設定されているか確認してください\n"
                     f"3. 必要なスコープが有効になっているか確認してください\n"
                     f"4. フォームに古い値が残っていないか確認してください（フォームをクリアして再試行）"
        }, status_code=500)


@app.get("/api/test/gemini")
async def test_gemini(api_key: Optional[str] = None):
    """
    Gemini API接続テスト
    フォームから送信された値があればそれを使用、なければ現在の設定を使用
    """
    global settings
    # 設定が読み込まれていない場合は読み込む
    if settings is None:
        reload_settings()
    
    # フォームから送信された値があればそれを使用、なければ現在の設定を使用
    gemini_api_key = (api_key and api_key.strip()) or (settings and settings.gemini_api_key and settings.gemini_api_key.strip())
    
    # 設定値の検証
    if not gemini_api_key:
        return JSONResponse({
            "success": False,
            "message": "GEMINI_API_KEYが設定されていません。API設定を確認してください。"
        }, status_code=400)
    
    try:
        # GeminiClientの初期化（usage_trackerのエラーは無視）
        # モデル名は現在の設定から取得（フォームからは送信されない）
        model_name = settings.gemini_model_name if settings else "gemini-2.5-pro"
        try:
            gemini_client = GeminiClient(
                api_key=gemini_api_key,
                model_name=model_name
            )
        except Exception as init_error:
            # usage_trackerのエラーは無視して、実際のAPI呼び出しで確認
            error_msg = str(init_error)
            if "使用制限" in error_msg or "429" in error_msg:
                logger.warning(f"使用制限の警告が表示されましたが、実際のAPI呼び出しで確認します: {init_error}")
                # 実際のAPI呼び出しで確認するため、クライアントを再初期化（usage_trackerなし）
                import google.generativeai as genai
                genai.configure(api_key=gemini_api_key)
                gemini_model = genai.GenerativeModel(model_name)
            else:
                raise
        
        # 実際にAPIを呼び出して接続を確認（簡単なテキスト生成でテスト）
        import asyncio
        import concurrent.futures
        loop = asyncio.get_event_loop()
        
        # 簡単なテキスト生成リクエストで接続テスト
        test_prompt = "Hello"
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Gemini APIの実際の呼び出しで接続を確認
            try:
                # 簡単なテキスト生成で接続を確認
                if 'gemini_model' in locals():
                    # usage_trackerのエラーがあった場合
                    test_result = await loop.run_in_executor(
                        executor,
                        lambda: gemini_model.generate_content(test_prompt)
                    )
                else:
                    # 通常の場合
                    test_result = await loop.run_in_executor(
                        executor,
                        lambda: gemini_client.model.generate_content(test_prompt)
                    )
                # レスポンスが正常に取得できたことを確認
                if not test_result or not test_result.text:
                    return JSONResponse({
                        "success": False,
                        "message": "Gemini API接続失敗: レスポンスが空です"
                    }, status_code=500)
                # API呼び出しが成功した場合は成功メッセージを返す
                # （ここに到達した時点で接続は成功している）
            except Exception as gen_error:
                error_msg = str(gen_error)
                error_type = type(gen_error).__name__
                
                # エラーの種類を正確に判定
                # 1. APIキーが無効な場合（400エラー、InvalidArgument）
                if error_type == "InvalidArgument" or "API key not valid" in error_msg or "API_KEY_INVALID" in error_msg or ("400" in error_msg and "API key" in error_msg):
                    return JSONResponse({
                        "success": False,
                        "message": f"Gemini API接続失敗: APIキーが無効です。\n\n【確認事項】\n1. GEMINI_API_KEYが正しく設定されているか確認してください\n2. APIキーが有効か確認してください\n3. Google AI Studioで新しいAPIキーを発行してください\n\nエラー詳細: {error_msg[:200]}"
                    }, status_code=401)
                # 2. クォータ制限の場合（429エラー、ResourceExhausted）
                elif error_type == "ResourceExhausted" or ("429" in error_msg and ("quota" in error_msg.lower() or "ResourceExhausted" in error_msg)):
                    # 実際のエラーメッセージを解析
                    retry_after = None
                    if "retry" in error_msg.lower() or "retry_delay" in error_msg.lower():
                        # リトライ可能な時間を抽出
                        import re
                        retry_match = re.search(r'retry.*?(\d+\.?\d*)\s*s', error_msg.lower())
                        if retry_match:
                            retry_after = float(retry_match.group(1))
                    
                    # エラーメッセージの詳細を取得
                    error_detail = error_msg[:500]  # より多くの情報を表示
                    
                    # リトライ可能な時間がある場合は、それを含める
                    if retry_after:
                        retry_message = f"\n\n【リトライ可能】約{int(retry_after)}秒後に再度お試しください。"
                    else:
                        retry_message = ""
                    
                    return JSONResponse({
                        "success": False,
                        "message": f"Gemini API接続失敗: レート制限またはクォータ制限に達しています。{retry_message}\n\n【エラー詳細】\n{error_detail}\n\n【対処方法】\n1. しばらく待ってから再度試してください{('（約' + str(int(retry_after)) + '秒後）' if retry_after else '')}\n2. 別のGeminiモデル（gemini-1.5-flashなど）を試してください\n3. Google Cloud Consoleでクォータを確認してください: https://ai.dev/usage?tab=rate-limit"
                    }, status_code=429)
                # 3. 認証エラーの場合（401, 403）
                elif "401" in error_msg or "403" in error_msg or "unauthorized" in error_msg.lower() or "forbidden" in error_msg.lower():
                    return JSONResponse({
                        "success": False,
                        "message": f"Gemini API接続失敗: 認証エラーです。\n\n【確認事項】\n1. GEMINI_API_KEYが正しく設定されているか確認してください\n2. APIキーに適切な権限があるか確認してください\n\nエラー詳細: {error_msg[:200]}"
                    }, status_code=401)
                # 4. その他のエラー
                else:
                    return JSONResponse({
                        "success": False,
                        "message": f"Gemini API接続失敗: {error_msg[:300]}"
                    }, status_code=500)
        
        # 使用状況を取得
        usage_info = {}
        if usage_tracker:
            usage_info = usage_tracker.get_usage_summary(model_name)
        
        return JSONResponse({
            "success": True,
            "message": "Gemini API接続成功",
            "model": model_name,
            "usage": usage_info
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "message": f"Gemini API接続失敗: {str(e)}"
        }, status_code=500)


@app.get("/api/test/chatwork")
async def test_chatwork(api_token: Optional[str] = None):
    """Chatwork API接続テスト（フォームから送信された値を使用）"""
    global settings
    # 設定が読み込まれていない場合は読み込む
    if settings is None:
        reload_settings()
    
    # api_tokenパラメータが明示的に指定されている場合のみ使用
    # 空文字列が送信された場合はエラーを返す
    if api_token is not None:
        # パラメータが指定されている場合
        if not api_token or not api_token.strip():
            return JSONResponse({
            "success": False,
                "message": "CHATWORK_API_TOKENが入力されていません。APIトークンを入力してください。"
            }, status_code=400)
        token_to_test = api_token.strip()
    else:
        # パラメータが指定されていない場合は設定から取得
        if not settings or not hasattr(settings, 'chatwork_api_token') or not settings.chatwork_api_token or not settings.chatwork_api_token.strip():
            return JSONResponse({
                "success": False,
                "message": "CHATWORK_API_TOKENが設定されていません。API設定を確認してください。"
            }, status_code=400)
        token_to_test = settings.chatwork_api_token.strip()
    
    try:
        chatwork_client = ChatworkClient(api_token=token_to_test)
        # 実際のAPI呼び出しで接続テスト
        test_result = chatwork_client.test_connection()
        return JSONResponse({
            "success": True,
            "message": f"Chatwork API接続成功（アカウント: {test_result.get('name', 'N/A')}）",
            "account_info": test_result
        })
    except ValueError as e:
        return JSONResponse({
            "success": False,
            "message": str(e)
        }, status_code=500)
    except Exception as e:
        return JSONResponse({
            "success": False,
            "message": f"Chatwork API接続エラー: {str(e)}"
        }, status_code=500)


@app.get("/api/test/chatwork-room")
async def test_chatwork_room(room_id: Optional[str] = None, api_token: Optional[str] = None):
    """ChatworkルームIDの接続テスト"""
    # フォームから送信された値を使用（なければ設定から取得）
    token_to_test = api_token if api_token and api_token.strip() else (settings.chatwork_api_token if settings else None)
    room_id_to_test = room_id if room_id and room_id.strip() else (settings.default_chatwork_room_id if settings else None)
    
    if not token_to_test or not token_to_test.strip():
        return JSONResponse({
            "success": False,
            "message": "CHATWORK_API_TOKENが設定されていません。API設定を確認してください。"
        }, status_code=400)
    
    if not room_id_to_test or not room_id_to_test.strip():
        return JSONResponse({
            "success": False,
            "message": "ルームIDが設定されていません。ルームIDを入力してください。"
        }, status_code=400)
    
    try:
        chatwork_client = ChatworkClient(api_token=token_to_test)
        # ルーム情報を取得して接続を確認
        room_info = chatwork_client.get_room_info(room_id_to_test)
        return JSONResponse({
            "success": True,
            "message": f"ルームID {room_id_to_test} への接続成功（ルーム名: {room_info.get('name', 'N/A')}）",
            "room_info": room_info
        })
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return JSONResponse({
                "success": False,
                "message": f"ルームID {room_id_to_test} が見つかりません。正しいルームIDを入力してください。"
            }, status_code=404)
        elif e.response.status_code == 403:
            return JSONResponse({
                "success": False,
                "message": f"ルームID {room_id_to_test} へのアクセス権限がありません。"
            }, status_code=403)
        else:
            return JSONResponse({
                "success": False,
                "message": f"ルームID接続エラー: {e.response.status_code} - {e.response.text[:200]}"
            }, status_code=e.response.status_code)
    except Exception as e:
        return JSONResponse({
            "success": False,
            "message": f"ルームID接続エラー: {str(e)}"
        }, status_code=500)


# ==================== 自動処理機能 ====================

@app.get("/api/meetings/recent")
async def get_recent_meetings():
    """最近終了した録画付きミーティングを取得（期間制限なし、録画がないものも含む）"""
    global settings
    
    # 設定が読み込まれていない場合は読み込む
    if settings is None:
        reload_settings()
    
    # 設定を再読み込み（最新の.envファイルから読み込む）
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"設定の再読み込みに失敗: {e}")
        return JSONResponse({
            "success": False,
            "message": f"設定の読み込みに失敗しました: {str(e)}"
        }, status_code=500)
    
    if not settings:
        return JSONResponse({
            "success": False,
            "message": "設定が読み込まれていません"
        }, status_code=500)
    
    # 設定値の検証
    if not hasattr(settings, 'zoom_api_key') or not settings.zoom_api_key or not settings.zoom_api_key.strip():
        return JSONResponse({
            "success": False,
            "message": "ZOOM_API_KEYが設定されていません。API設定を確認してください。"
        }, status_code=400)
    
    if not hasattr(settings, 'zoom_api_secret') or not settings.zoom_api_secret or not settings.zoom_api_secret.strip():
        return JSONResponse({
            "success": False,
            "message": "ZOOM_API_SECRETが設定されていません。API設定を確認してください。"
        }, status_code=400)
    
    try:
        zoom_client = ZoomClient(
            api_key=settings.zoom_api_key.strip(),
            api_secret=settings.zoom_api_secret.strip(),
            account_id=settings.zoom_account_id.strip() if settings.zoom_account_id else None
        )
        # 期間制限なしで録画付きミーティングのみを取得
        # hours=Noneで期間制限なし（Zoom APIの最大300件まで取得可能）
        # include_without_recordings=Falseで録画があるものだけを取得
        # タイムアウトを設定して、長時間ブロックしないようにする
        import asyncio
        try:
            meetings = await asyncio.wait_for(
                asyncio.to_thread(
                    zoom_client.get_recent_meetings_with_recordings,
                    hours=None,
                    include_without_recordings=False  # 録画があるものだけを取得
                ),
                timeout=120.0  # 120秒（2分）のタイムアウト（300件のミーティングに対して録画情報を取得するため時間がかかる）
            )
        except asyncio.TimeoutError:
            logger.warning("ミーティング取得がタイムアウトしました（120秒）")
            return JSONResponse({
                "success": False,
                "message": "ミーティング取得がタイムアウトしました（120秒）。\n\n【対処方法】\n1. しばらく待ってから再度お試しください\n2. ミーティング数が多い場合は、時間がかかることがあります\n3. 必要に応じて、期間を限定して取得してください",
                "meetings": [],
                "count": 0
            }, status_code=504)
        
        # コンピュータ録画も検出して、ミーティングリストに追加
        try:
            from local_recording_detector import LocalRecordingDetector
            from pathlib import Path
            import re
            
            detector = LocalRecordingDetector()
            
            # ローカル録画ファイルを検索
            local_recordings = detector.find_recordings(hours=None, min_size_mb=1.0, search_multiple_dirs=True)
            
            # 既存のミーティングIDのセットを作成（重複チェック用）
            existing_meeting_ids = {str(m.get("id")) for m in meetings}
            
            # ローカル録画ファイルからミーティングIDを抽出
            # Zoomのローカル録画は、recording.confファイルがあるディレクトリに保存されている
            local_recording_map = {}  # meeting_id -> [録画ファイル情報]
            
            # 録画保存先ディレクトリを取得
            recording_dir = detector.get_recording_directory()
            
            # recording.confファイルがあるディレクトリから録画ファイルを探す
            if recording_dir and Path(recording_dir).exists():
                # recording.confファイルがあるディレクトリを検索
                for conf_file in Path(recording_dir).rglob("recording.conf"):
                    try:
                        conf_dir = conf_file.parent
                        
                        # 同じディレクトリ内の録画ファイルを探す
                        dir_recordings = []
                        for rec_file in local_recordings:
                            rec_path = Path(rec_file["path"])
                            if rec_path.parent == conf_dir:
                                dir_recordings.append(rec_file)
                        
                        # recording.confファイルから録画ファイル名を取得
                        import json
                        try:
                            with open(conf_file, 'r', encoding='utf-8') as f:
                                conf_content = f.read()
                            
                            # JSONとして解析
                            try:
                                conf_data = json.loads(conf_content)
                                if 'items' in conf_data:
                                    for item in conf_data['items']:
                                        # 動画ファイルを確認
                                        if 'video' in item:
                                            video_file = conf_dir / item['video']
                                            if video_file.exists():
                                                try:
                                                    stat = video_file.stat()
                                                    file_size_mb = stat.st_size / 1024 / 1024
                                                    if file_size_mb >= 1.0:  # 1MB以上
                                                        from datetime import datetime
                                                        file_mtime = datetime.fromtimestamp(stat.st_mtime)
                                                        dir_recordings.append({
                                                            "path": str(video_file),
                                                            "name": video_file.name,
                                                            "size_mb": file_size_mb,
                                                            "modified_time": file_mtime,
                                                            "extension": video_file.suffix.lower()
                                                        })
                                                        logger.info(f"recording.confから動画ファイルを発見: {video_file.name} ({file_size_mb:.2f} MB)")
                                                except Exception as e:
                                                    logger.debug(f"動画ファイル情報の取得に失敗: {video_file} - {e}")
                                        
                                        # 音声ファイルを確認
                                        if 'audio' in item:
                                            audio_file = conf_dir / item['audio']
                                            if audio_file.exists():
                                                try:
                                                    stat = audio_file.stat()
                                                    file_size_mb = stat.st_size / 1024 / 1024
                                                    if file_size_mb >= 1.0:  # 1MB以上
                                                        from datetime import datetime
                                                        file_mtime = datetime.fromtimestamp(stat.st_mtime)
                                                        dir_recordings.append({
                                                            "path": str(audio_file),
                                                            "name": audio_file.name,
                                                            "size_mb": file_size_mb,
                                                            "modified_time": file_mtime,
                                                            "extension": audio_file.suffix.lower()
                                                        })
                                                        logger.info(f"recording.confから音声ファイルを発見: {audio_file.name} ({file_size_mb:.2f} MB)")
                                                except Exception as e:
                                                    logger.debug(f"音声ファイル情報の取得に失敗: {audio_file} - {e}")
                            except json.JSONDecodeError:
                                logger.debug(f"recording.confがJSON形式ではありません: {conf_file}")
                        except Exception as e:
                            logger.debug(f"recording.confの読み込みに失敗: {conf_file} - {e}")
                        
                        # ディレクトリ内に直接録画ファイルがあるか確認（find_recordingsで見つからなかった場合）
                        # サブディレクトリも含めて再帰的に検索
                        if not dir_recordings:
                            for ext in ["*.mp4", "*.m4a", "*.mov", "*.mp3", "*.zoom"]:
                                # サブディレクトリも含めて再帰的に検索
                                for video_file in conf_dir.rglob(ext):
                                    try:
                                        stat = video_file.stat()
                                        file_size_mb = stat.st_size / 1024 / 1024
                                        if file_size_mb >= 1.0:  # 1MB以上
                                            from datetime import datetime
                                            file_mtime = datetime.fromtimestamp(stat.st_mtime)
                                            dir_recordings.append({
                                                "path": str(video_file),
                                                "name": video_file.name,
                                                "size_mb": file_size_mb,
                                                "modified_time": file_mtime,
                                                "extension": video_file.suffix.lower()
                                            })
                                            logger.debug(f"コンピュータ録画ファイルを発見: {video_file} ({file_size_mb:.2f} MB)")
                                    except Exception as e:
                                        logger.debug(f"ファイル情報の取得に失敗: {video_file} - {e}")
                        
                        # 録画ファイルが見つかった場合
                        if dir_recordings:
                            # ディレクトリ名から日時を抽出（例: "2025-10-18 21.02.56 AI勉強会"）
                            dir_name = conf_dir.name
                            
                            # 日時パターンを抽出（YYYY-MM-DD HH.MM.SS）
                            datetime_match = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2})\.(\d{2})\.(\d{2})', dir_name)
                            if datetime_match:
                                date_str = datetime_match.group(1)  # YYYY-MM-DD
                                hour = datetime_match.group(2)
                                minute = datetime_match.group(3)
                                second = datetime_match.group(4)
                                
                                # ディレクトリ名からトピックを抽出（日時の後の部分）
                                topic_match = re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}\.\d{2}\.\d{2}\s+(.+)', dir_name)
                                topic = topic_match.group(1) if topic_match else dir_name
                                
                                # ミーティングIDの代わりに、ディレクトリ名のハッシュ値を使用
                                # または、日時から生成されたIDを使用
                                import hashlib
                                meeting_id_str = hashlib.md5(dir_name.encode()).hexdigest()[:11]
                                # 11桁の数字として扱うため、ハッシュを数値に変換
                                meeting_id = str(int(meeting_id_str, 16))[:11].zfill(11)
                                
                                if meeting_id not in local_recording_map:
                                    local_recording_map[meeting_id] = {
                                        "recordings": [],
                                        "topic": topic,
                                        "start_time": f"{date_str}T{hour}:{minute}:{second}Z",
                                        "dir_name": dir_name
                                    }
                                
                                local_recording_map[meeting_id]["recordings"].extend(dir_recordings)
                                logger.info(f"コンピュータ録画を発見: ディレクトリ={dir_name}, 録画ファイル数={len(dir_recordings)}件")
                    except Exception as e:
                        logger.debug(f"recording.confディレクトリの処理に失敗: {conf_file} - {e}")
            
            # ファイル名からもミーティングIDを抽出（フォールバック）
            for local_rec in local_recordings:
                # ファイル名から11桁の数字を探す（ZoomのミーティングIDは11桁）
                meeting_id_match = re.search(r'(\d{11})', local_rec["name"])
                if meeting_id_match:
                    meeting_id = meeting_id_match.group(1)
                    if meeting_id not in local_recording_map:
                        local_recording_map[meeting_id] = {
                            "recordings": [],
                            "topic": local_rec["name"],
                            "start_time": local_rec["modified_time"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "dir_name": None
                        }
                    if "recordings" not in local_recording_map[meeting_id]:
                        local_recording_map[meeting_id]["recordings"] = []
                    local_recording_map[meeting_id]["recordings"].append(local_rec)
                    logger.debug(f"ファイル名から録画を発見: ミーティングID={meeting_id}, ファイル={local_rec['name']}")
            
            # コンピュータ録画をミーティングリストに追加
            local_added_count = 0
            for meeting_id, rec_data in local_recording_map.items():
                rec_files = rec_data.get("recordings", [])
                if not rec_files:
                    continue
                
                # 既にリストに含まれていない場合のみ追加
                if meeting_id not in existing_meeting_ids:
                    # 最新の録画ファイルを使用
                    latest_rec = max(rec_files, key=lambda x: x["modified_time"])
                    
                    # 全ての録画ファイル情報を作成
                    recordings_info = []
                    for rec_file in rec_files:
                        recordings_info.append({
                            "file_type": rec_file["extension"].upper().replace(".", ""),
                            "status": "completed",
                            "file_size": int(rec_file["size_mb"] * 1024 * 1024),
                            "local_path": rec_file["path"],
                            "is_local": True
                        })
                    
                    # トピックを取得（ディレクトリ名から抽出したもの、またはファイル名）
                    topic = rec_data.get("topic", latest_rec['name'])
                    start_time = rec_data.get("start_time", latest_rec["modified_time"].strftime("%Y-%m-%dT%H:%M:%SZ"))
                    
                    # コンピュータ録画として追加
                    meetings.append({
                        "id": int(meeting_id) if meeting_id.isdigit() else int(meeting_id[:11].ljust(11, '0')),
                        "topic": f"コンピュータ録画: {topic}",
                        "start_time": start_time,
                        "recordings": recordings_info,
                        "is_local_recording": True
                    })
                    existing_meeting_ids.add(meeting_id)
                    local_added_count += 1
                    logger.info(f"コンピュータ録画を追加: ディレクトリ={rec_data.get('dir_name', 'N/A')}, ファイル数={len(rec_files)}件")
            
            if local_added_count > 0:
                logger.info(f"コンピュータ録画: {len(local_recordings)}件検出、{local_added_count}件のミーティングを追加")
        except Exception as e:
            logger.warning(f"コンピュータ録画の検出に失敗: {e}")
            import traceback
            logger.warning(f"コンピュータ録画検出エラーの詳細: {traceback.format_exc()}")
        
        # 録画があるものだけをフィルタリング（念のため）
        meetings_with_recordings = [
            m for m in meetings 
            if m.get("recordings") and len(m.get("recordings", [])) > 0
        ]
        
        # 開始日時でソート（新しい順）
        meetings_with_recordings.sort(key=lambda x: x.get("start_time", ""), reverse=True)
        
        # ログに記録
        logger.info(f"ミーティング一覧取得成功: {len(meetings_with_recordings)}件（録画付きのみ、クラウド: {len([m for m in meetings_with_recordings if not m.get('is_local_recording')])}件、コンピュータ: {len([m for m in meetings_with_recordings if m.get('is_local_recording')])}件）")
        
        return JSONResponse({
            "success": True,
            "meetings": meetings_with_recordings,
            "count": len(meetings_with_recordings)
        })
    except Exception as e:
        logger.error(f"ミーティング一覧取得エラー: {e}", exc_info=True)
        return JSONResponse({
            "success": False,
            "message": f"エラー: {str(e)}"
        }, status_code=500)


@app.post("/api/auto-process/mapping")
async def add_auto_process_mapping(
    meeting_id: str = Form(...),
    room_id: str = Form(...),
    meeting_topic: Optional[str] = Form(None)
):
    """自動処理のマッピングを追加"""
    auto_process_config.add_mapping(meeting_id, room_id, meeting_topic)
    return JSONResponse({
        "success": True,
        "message": "マッピングを追加しました"
    })


@app.delete("/api/auto-process/mapping/{meeting_id}")
async def remove_auto_process_mapping(meeting_id: str):
    """自動処理のマッピングを削除"""
    auto_process_config.remove_mapping(meeting_id)
    return JSONResponse({
        "success": True,
        "message": "マッピングを削除しました"
    })


@app.get("/api/auto-process/mappings")
async def get_auto_process_mappings():
    """すべての自動処理マッピングを取得"""
    mappings = auto_process_config.get_all_mappings()
    return JSONResponse({
        "success": True,
        "mappings": mappings
    })


@app.post("/api/webhook/zoom")
async def zoom_webhook(request: Request):
    """
    Zoom Webhookエンドポイント
    ミーティング作成イベントと録画完了イベントを受信して自動処理を開始
    """
    global settings
    # 設定が読み込まれていない場合は読み込む
    if settings is None:
        reload_settings()
    
    try:
        data = await request.json()
        event_type = data.get("event")
        
        # Challenge-responseチェック（Webhook URL検証）
        if event_type == "endpoint.url_validation":
            import hmac
            import hashlib
            plain_token = data.get("payload", {}).get("plainToken")
            if plain_token and settings and settings.zoom_api_secret:
                # encryptedTokenを生成（HMAC-SHA256）
                encrypted_token = hmac.new(
                    settings.zoom_api_secret.encode('utf-8'),
                    plain_token.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                logger.info(f"Challenge-responseチェック: plainToken={plain_token}, encryptedToken={encrypted_token}")
                return JSONResponse({
                    "plainToken": plain_token,
                    "encryptedToken": encrypted_token
                })
            else:
                logger.warning("Challenge-responseチェック: plainTokenまたはAPI Secretが設定されていません")
                return JSONResponse({
                    "error": "plainTokenまたはAPI Secretが設定されていません"
                }, status_code=400)
        
        # ミーティング作成イベントをチェック
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
                return JSONResponse({
                    "success": True,
                    "message": f"自動処理設定を追加しました: ミーティングID={meeting_id}, ルームID={settings.default_chatwork_room_id}"
                })
            else:
                logger.info(f"デフォルトルームIDが設定されていないため、自動処理設定を追加しませんでした: ミーティングID={meeting_id}")
                return JSONResponse({
                    "success": True,
                    "message": "デフォルトルームIDが設定されていません"
                })
        
        # 録画完了イベントをチェック
        if event_type == "recording.completed":
            payload = data.get("payload", {})
            object_data = payload.get("object", {})
            meeting_id = str(object_data.get("id"))
            
            logger.info(f"録画完了イベントを受信: ミーティングID={meeting_id}")
            
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
        
        # その他のイベント
        return JSONResponse({
            "success": True,
            "message": f"イベントを受信: {event_type}"
        })
        
    except Exception as e:
        logger.error(f"Webhook処理エラー: {e}", exc_info=True)
        return JSONResponse({
            "success": False,
            "message": f"エラー: {str(e)}"
        }, status_code=500)


async def check_and_process_automatically():
    """定期的に録画をチェックして自動処理"""
    global settings
    # 設定が読み込まれていない場合は読み込む
    if settings is None:
        reload_settings()
    
    if not settings:
        return
    
    try:
        # タイムアウトを設定して、長時間ブロックしないようにする
        zoom_client = ZoomClient(
            api_key=settings.zoom_api_key,
            api_secret=settings.zoom_api_secret,
            account_id=settings.zoom_account_id
        )
        
        # 1. Zoom APIから最近の録画付きミーティングを取得（タイムアウト付き）
        try:
            # 非同期で実行してタイムアウトを設定
            import asyncio
            # 期間制限なしで全てのミーティングを取得（録画がないものも含む）
            meetings = await asyncio.wait_for(
                asyncio.to_thread(zoom_client.get_recent_meetings_with_recordings, hours=None, include_without_recordings=True),
                timeout=30.0  # 30秒でタイムアウト
            )
            
            # 録画があるミーティングだけをフィルタリング（改善: 問題点2の修正）
            meetings_with_recordings = [
                m for m in meetings 
                if m.get("recordings") and len(m.get("recordings", [])) > 0
            ]
            
            logger.info(f"録画付きミーティング: {len(meetings_with_recordings)}件（全ミーティング: {len(meetings)}件）")
            
            for meeting in meetings_with_recordings:
                meeting_id = str(meeting.get("id"))
                
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
                        # 処理を実行して結果を待つ（改善: 問題点3の修正）
                        result = await process_meeting_recording_task(task_id, meeting_id, room_id)
                        
                        # 成功した場合のみ処理済みマークを付ける（改善: 問題点3の修正）
                        if result.get("success"):
                            auto_process_config.mark_as_processed(meeting_id)
                            logger.info(f"✅ 自動処理が完了しました: ミーティングID={meeting_id}")
                        else:
                            logger.error(f"❌ 自動処理が失敗しました: ミーティングID={meeting_id}, エラー: {result.get('error', '不明なエラー')}")
                            # 失敗した場合は処理済みマークを付けない（再処理の機会を残す）
                    except Exception as e:
                        logger.error(f"❌ 自動処理でエラーが発生しました: ミーティングID={meeting_id}, エラー: {e}", exc_info=True)
                        # エラーが発生した場合は処理済みマークを付けない（改善: 問題点4の修正）
        except asyncio.TimeoutError:
            logger.warning("Zoom APIからの録画取得がタイムアウトしました")
        except Exception as e:
            logger.warning(f"Zoom APIからの録画取得に失敗: {e}")
        
        # 2. ローカル録画ファイルをチェック（Zoom APIから取得できない場合のフォールバック）
        try:
            # 遅延インポート（ファイルシステムアクセスでブロッキングする可能性があるため）
            from local_recording_detector import LocalRecordingDetector
            detector = LocalRecordingDetector()
            # 非同期で実行してタイムアウトを設定（hours=Noneで全ての録画を検索）
            local_recordings = await asyncio.wait_for(
                asyncio.to_thread(detector.find_recordings, hours=None, min_size_mb=1.0),
                timeout=30.0  # 30秒でタイムアウト（全て検索するため時間を延長）
            )
            
            # 最新のローカル録画を確認
            if local_recordings:
                latest_recording = local_recordings[0]
                recording_path = latest_recording["path"]
                recording_name = latest_recording["name"]
                
                # ファイル名からミーティングIDを推測（可能な場合）
                # または、最新の録画をデフォルトルームに送信
                room_id = settings.default_chatwork_room_id
                
                if room_id:
                    # 録画ファイル名をキーとして処理済みかチェック
                    processed_key = f"local_{recording_name}"
                    
                    if not auto_process_config.is_processed(processed_key):
                        logger.info(f"ローカル録画の自動処理を開始: {recording_name}")
                        
                        # 一時的なミーティングIDとしてファイル名を使用
                        temp_meeting_id = recording_name.replace(".mp4", "").replace(".m4a", "")
                
                    # 処理を開始
                    task_id = str(uuid.uuid4())
                    asyncio.create_task(
                        process_meeting_recording_task(task_id, temp_meeting_id, room_id)
                    )
                    auto_process_config.mark_as_processed(processed_key)
        except asyncio.TimeoutError:
            logger.warning("ローカル録画の検索がタイムアウトしました")
        except Exception as e:
            logger.warning(f"ローカル録画の検索に失敗: {e}")
                
    except Exception as e:
        logger.error(f"自動チェックエラー: {e}", exc_info=True)


async def process_new_recording(recording_path: str):
    """新しい録画ファイルを処理"""
    if not settings or not settings.default_chatwork_room_id:
        logger.warning("デフォルトルームIDが設定されていません。録画ファイルは処理されません。")
        return
    
    try:
        # ファイル名から処理済みかチェック
        recording_name = Path(recording_path).name
        processed_key = f"local_{recording_name}"
        
        if auto_process_config.is_processed(processed_key):
            logger.info(f"録画ファイルは既に処理済みです: {recording_name}")
            return
        
        logger.info(f"新しい録画ファイルを検知: {recording_path}")
        
        # 一時的なミーティングIDとしてファイル名を使用
        temp_meeting_id = recording_name.replace(".mp4", "").replace(".m4a", "").replace(".mov", "")
        
        # 処理を開始
        task_id = str(uuid.uuid4())
        asyncio.create_task(
            process_meeting_recording_task(task_id, temp_meeting_id, settings.default_chatwork_room_id)
        )
        auto_process_config.mark_as_processed(processed_key)
        
        logger.info(f"録画ファイルの自動処理を開始: {recording_name}")
    except Exception as e:
        logger.error(f"録画ファイルの処理エラー: {e}", exc_info=True)


@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の処理"""
    global scheduler_task, recording_watcher, settings
    
    # 設定を読み込む（起動時に実行）
    logger.info("設定を読み込み中...")
    try:
        reload_settings()
        
        # 一時ディレクトリを作成（Vercelでは/tmpを使用）
        if settings and settings.temp_dir:
            temp_dir = Path(settings.temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"一時ディレクトリを作成/確認: {temp_dir}")
    except Exception as e:
        logger.error(f"起動時の設定読み込みエラー: {e}", exc_info=True)
        # エラーが発生してもアプリケーションは起動を続ける（環境変数が設定されていない場合など）
        # 各エンドポイントで個別にエラーハンドリングを行う
    
    # スケジューラーを停止（Webhook方式のみを使用するため）
    # 1分ごとの自動処理は不要。Webhook（Event Subscriptions）のみで自動化する
    logger.info("スケジューラーは停止しています（Webhook方式のみを使用）")
    scheduler_task = None
    
    # 録画ファイルの監視を停止（Webhook方式のみを使用するため）
    # ローカル録画の監視は不要。Webhook（Event Subscriptions）のみで自動化する
    logger.info("録画ファイル監視は停止しています（Webhook方式のみを使用）")
    recording_watcher = None
    
    # 以下のコードはコメントアウト（Webhook方式のみを使用するため）
    # 録画ファイルの監視は不要。Webhook（Event Subscriptions）のみで自動化する
    # if settings and settings.default_chatwork_room_id:
    #     try:
    #         # 遅延インポート（ファイルシステムアクセスでブロッキングする可能性があるため）
    #         from local_recording_detector import LocalRecordingDetector
    #         from recording_watcher import RecordingWatcher
    #         detector = LocalRecordingDetector()
    #         recording_dir = detector.get_recording_directory()
    #         
    #         if recording_dir:
    #             # コールバック関数を定義
    #             def on_recording_detected(file_path: str):
    #                 """録画ファイル検出時のコールバック"""
    #                 asyncio.create_task(process_new_recording(file_path))
    #             
    #             # 監視を開始
    #             try:
    #                 recording_watcher = RecordingWatcher(
    #                     recording_directory=recording_dir,
    #                     callback=on_recording_detected,
    #                     min_size_mb=1.0
    #                 )
    #                 recording_watcher.start()
    #                 if recording_watcher.is_alive():
    #                     logger.info(f"録画ファイルのリアルタイム監視を開始しました: {recording_dir}")
    #                 else:
    #                     logger.info(f"録画ファイルの監視はポーリング方式（1分ごと）で動作します: {recording_dir}")
    #             except Exception as e:
    #                 logger.warning(f"録画ファイル監視の開始に失敗: {e}")
    #         else:
    #             logger.warning("録画保存先が見つかりませんでした。監視を開始できません。")
    #     except Exception as e:
    #         logger.error(f"録画ファイル監視の初期化に失敗: {e}", exc_info=True)
    # else:
    #     logger.info("デフォルトルームIDが設定されていないため、録画ファイルの監視をスキップします")


@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時の処理"""
    global scheduler_task, recording_watcher
    
    # スケジューラーを停止
    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
    logger.info("スケジューラーを停止しました")
    
    # 録画ファイル監視を停止
    if recording_watcher:
        recording_watcher.stop()
        logger.info("録画ファイルの監視を停止しました")


if __name__ == "__main__":
    # ローカル開発サーバーの起動
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )

