"""
Zoom録画から議事録を作成してChatworkに送信するメインプログラム
"""
import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional
from config import get_settings
from zoom_client import ZoomClient
from gemini_client import GeminiClient
from chatwork_client import ChatworkClient
from local_recording_detector import LocalRecordingDetector

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def cleanup_temp_files(file_path: str):
    """
    一時ファイルを削除
    
    Args:
        file_path: 削除するファイルパス
    """
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"一時ファイルを削除しました: {file_path}")
    except Exception as e:
        logger.warning(f"一時ファイルの削除に失敗しました: {e}")


def process_meeting_recording(
    meeting_id: str,
    room_id: str,
    output_dir: Optional[str] = None
) -> bool:
    """
    Zoom録画から議事録を作成してChatworkに送信
    
    Args:
        meeting_id: ZoomミーティングID
        room_id: ChatworkルームID
        output_dir: 一時ファイル保存先ディレクトリ
        
    Returns:
        成功した場合True
    """
    settings = get_settings()
    
    # Chatwork APIトークンの確認
    if not hasattr(settings, 'chatwork_api_token') or not settings.chatwork_api_token:
        logger.error("CHATWORK_API_TOKENが設定されていません")
        logger.error("環境変数CHATWORK_API_TOKENを設定してください")
        logger.error("取得方法: Chatwork → サービス連携 → APIトークン")
        return False
    
    # 一時ディレクトリの設定
    if output_dir is None:
        output_dir = settings.temp_dir
    os.makedirs(output_dir, exist_ok=True)
    
    recording_file_path = None
    
    try:
        # 1. Zoom APIで録画ファイルを取得
        logger.info(f"Zoom録画を取得中: ミーティングID={meeting_id}")
        zoom_client = ZoomClient(
            api_key=settings.zoom_api_key,
            api_secret=settings.zoom_api_secret,
            account_id=settings.zoom_account_id
        )
        
        # まずZoom文字起こしを取得を試みる
        transcript_text = None
        try:
            transcript_text = zoom_client.get_transcript(meeting_id)
            if transcript_text:
                logger.info(f"Zoom文字起こしを取得しました（{len(transcript_text)}文字）")
        except Exception as e:
            logger.warning(f"Zoom文字起こしの取得に失敗: {e}")
            transcript_text = None
        
        recording_file_path = None
        if not transcript_text:
            # まずZoom APIから録画を取得を試みる
            try:
                recording_file_path = zoom_client.get_recording_file(
                    meeting_id=meeting_id,
                    output_dir=output_dir
                )
                if recording_file_path:
                    logger.info(f"Zoom APIから録画ファイルを取得しました: {recording_file_path}")
            except Exception as e:
                logger.warning(f"Zoom APIからの録画取得に失敗: {e}")
                recording_file_path = None
            
            # Zoom APIから取得できなかった場合は、ローカル録画を検索
            if not recording_file_path:
                logger.info("ローカル録画ファイルを検索開始")
                try:
                    detector = LocalRecordingDetector()
                    local_recording = detector.find_recording_by_meeting_id(
                        meeting_id,
                        None,  # 自動検出
                        168  # 1週間以内
                    )
                    
                    if local_recording:
                        recording_file_path = local_recording["path"]
                        logger.info(f"ローカル録画ファイルを発見: {recording_file_path}")
                    else:
                        # 最新の録画ファイルを使用
                        latest_recording = detector.find_latest_recording(
                            None,  # 自動検出
                            24,  # 24時間以内
                            1.0  # 1MB以上
                        )
                        
                        if latest_recording:
                            recording_file_path = latest_recording["path"]
                            logger.info(f"最新のローカル録画ファイルを使用: {recording_file_path}")
                except Exception as e:
                    logger.warning(f"ローカル録画の検索に失敗: {e}")
            
            if not recording_file_path:
                logger.error("録画ファイルが見つかりませんでした")
                return False
            
            logger.info(f"録画ファイルを取得しました: {recording_file_path}")
        
        # 2. Gemini APIで議事録を生成
        logger.info("Gemini APIで議事録を生成中...")
        gemini_client = GeminiClient(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model_name
        )
        
        # 文字起こしがあればそれを使用、なければ動画から生成
        if transcript_text:
            logger.info("文字起こしから議事録を生成")
            transcript = gemini_client.summarize_transcript(transcript_text)
        else:
            # ファイル拡張子で動画か音声かを判定
            file_ext = Path(recording_file_path).suffix.lower()
            if file_ext in [".mp4", ".mov", ".avi", ".mkv"]:
                transcript = gemini_client.transcribe_and_summarize(recording_file_path)
            elif file_ext in [".mp3", ".wav", ".m4a", ".ogg"]:
                transcript = gemini_client.transcribe_audio(recording_file_path)
            else:
                # デフォルトで動画として処理
                transcript = gemini_client.transcribe_and_summarize(recording_file_path)
        
        logger.info("議事録の生成が完了しました")
        
        # 3. Chatworkに送信
        logger.info(f"Chatworkに送信中: ルームID={room_id}")
        
        # Chatwork APIトークンの再確認
        if not settings.chatwork_api_token:
            raise ValueError("CHATWORK_API_TOKENが設定されていません。環境変数を確認してください。")
        
        chatwork_client = ChatworkClient(api_token=settings.chatwork_api_token)
        
        # メッセージにヘッダーを追加
        message = f"""[info][title]Zoom会議議事録[/title]
ミーティングID: {meeting_id}

{transcript}
[/info]"""
        
        chatwork_client.send_message(room_id=room_id, message=message)
        logger.info("Chatworkへの送信が完了しました")
        
        return True
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=True)
        return False
        
    finally:
        # 一時ファイルを削除
        if recording_file_path:
            cleanup_temp_files(recording_file_path)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="Zoom録画から議事録を作成してChatworkに送信"
    )
    parser.add_argument(
        "meeting_id",
        help="ZoomミーティングID"
    )
    parser.add_argument(
        "--room-id",
        help="ChatworkルームID（指定しない場合は環境変数のデフォルト値を使用）"
    )
    parser.add_argument(
        "--output-dir",
        help="一時ファイル保存先ディレクトリ（デフォルト: ./temp）"
    )
    
    args = parser.parse_args()
    
    # 設定の取得と検証
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"設定の読み込みに失敗しました: {e}")
        logger.error("環境変数が正しく設定されているか確認してください")
        sys.exit(1)
    
    # Chatwork APIトークンの確認
    if not hasattr(settings, 'chatwork_api_token') or not settings.chatwork_api_token:
        logger.error("=" * 60)
        logger.error("❌ CHATWORK_API_TOKENが設定されていません")
        logger.error("=" * 60)
        logger.error("")
        logger.error("【取得方法】")
        logger.error("1. Chatworkにログイン")
        logger.error("2. 右上の「利用者名」メニュー → 「サービス連携」")
        logger.error("3. 「APIトークン」タブ → 「新しいAPIトークンを作成」")
        logger.error("4. トークンをコピー（一度だけ表示されます）")
        logger.error("")
        logger.error("【設定方法】")
        logger.error(".envファイルに以下を追加:")
        logger.error("CHATWORK_API_TOKEN=your_chatwork_api_token_here")
        logger.error("")
        sys.exit(1)
    
    # ルームIDの取得
    room_id = args.room_id or settings.default_chatwork_room_id
    
    if not room_id:
        logger.error("=" * 60)
        logger.error("❌ ChatworkルームIDが指定されていません")
        logger.error("=" * 60)
        logger.error("")
        logger.error("【指定方法（いずれか）】")
        logger.error("1. コマンドライン引数: --room-id <room_id>")
        logger.error("2. 環境変数: DEFAULT_CHATWORK_ROOM_ID=<room_id>")
        logger.error("")
        logger.error("【ルームIDの取得方法】")
        logger.error("1. トークルームを開く")
        logger.error("2. 右上の歯車アイコン → 「グループチャットの設定」")
        logger.error("3. ルームIDをコピー（数字のみ）")
        logger.error("   または、URLの「rid」の後の数字をコピー")
        logger.error("   例: https://www.chatwork.com/#!rid123456789 → 123456789")
        logger.error("")
        sys.exit(1)
    
    # 処理実行
    success = process_meeting_recording(
        meeting_id=args.meeting_id,
        room_id=room_id,
        output_dir=args.output_dir
    )
    
    if success:
        logger.info("処理が正常に完了しました")
        sys.exit(0)
    else:
        logger.error("処理が失敗しました")
        sys.exit(1)


if __name__ == "__main__":
    main()

