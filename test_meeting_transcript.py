#!/usr/bin/env python3
"""
Zoom録画から議事録を生成してChatworkに送信するテストスクリプト
使用方法: python test_meeting_transcript.py <meeting_id> [room_id]
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from config import get_settings
from zoom_client import ZoomClient
from gemini_client import GeminiClient
from chatwork_client import ChatworkClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    if len(sys.argv) < 2:
        print("使用方法: python test_meeting_transcript.py <meeting_id> [room_id]")
        print("例: python test_meeting_transcript.py 1234567890 406484503")
        sys.exit(1)
    
    meeting_id = sys.argv[1]
    room_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        settings = get_settings()
        
        # ルームIDが指定されていない場合はデフォルト値を使用
        if not room_id:
            room_id = settings.default_chatwork_room_id
            if not room_id:
                print("❌ ChatworkルームIDが指定されていません")
                print("   コマンドライン引数で指定するか、.envファイルにDEFAULT_CHATWORK_ROOM_IDを設定してください")
                sys.exit(1)
        
        print('=' * 70)
        print('Zoom録画から議事録を生成してChatworkに送信')
        print('=' * 70)
        print(f'ミーティングID: {meeting_id}')
        print(f'ChatworkルームID: {room_id}')
        print()
        
        # ========== ステップ1: Zoom APIで録画ファイルを取得 ==========
        print('【ステップ1】Zoom録画を取得中...')
        zoom_client = ZoomClient(
            api_key=settings.zoom_api_key,
            api_secret=settings.zoom_api_secret,
            account_id=settings.zoom_account_id
        )
        
        output_dir = settings.temp_dir
        os.makedirs(output_dir, exist_ok=True)
        
        recording_file_path = zoom_client.get_recording_file(meeting_id, output_dir)
        
        if not recording_file_path:
            print('❌ 録画ファイルが見つかりませんでした')
            print('   録画が完了しているか、ミーティングIDが正しいか確認してください')
            sys.exit(1)
        
        file_size_mb = os.path.getsize(recording_file_path) / 1024 / 1024
        print(f'✅ 録画ファイルを取得しました: {recording_file_path}')
        print(f'   ファイルサイズ: {file_size_mb:.2f}MB')
        print()
        
        # ========== ステップ2: Gemini APIで議事録を生成 ==========
        print('【ステップ2】Gemini APIで議事録を生成中...')
        gemini_client = GeminiClient(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model_name
        )
        
        file_ext = os.path.splitext(recording_file_path)[1].lower()
        if file_ext in [".mp4", ".mov", ".avi", ".mkv"]:
            print('   動画ファイルとして処理します...')
            transcript = gemini_client.transcribe_and_summarize(recording_file_path)
        else:
            print('   音声ファイルとして処理します...')
            transcript = gemini_client.transcribe_and_summarize(recording_file_path)
        
        print(f'✅ 議事録を生成しました（{len(transcript)}文字）')
        print()
        print('【生成された議事録（プレビュー）】')
        print('-' * 70)
        print(transcript[:500] + '...' if len(transcript) > 500 else transcript)
        print('-' * 70)
        print()
        
        # ========== ステップ3: Chatworkに送信 ==========
        print('【ステップ3】Chatworkに送信中...')
        chatwork_client = ChatworkClient(settings.chatwork_api_token)
        
        # メッセージにミーティングIDを追加
        message = f"[info][title]📝 議事録 - ミーティングID: {meeting_id}[/title]{transcript}[/info]"
        
        result = chatwork_client.send_message(room_id, message)
        print(f'✅ Chatworkに送信しました')
        print(f'   ルームID: {room_id}')
        print()
        
        # 一時ファイルを削除
        try:
            os.remove(recording_file_path)
            print(f'✅ 一時ファイルを削除しました: {recording_file_path}')
        except Exception as e:
            logger.warning(f'一時ファイルの削除に失敗: {e}')
        
        print()
        print('=' * 70)
        print('✅ 処理が完了しました！')
        print('=' * 70)
        
    except Exception as e:
        logger.error(f'エラーが発生しました: {e}', exc_info=True)
        print()
        print('❌ エラーが発生しました')
        print(f'   エラー内容: {str(e)}')
        sys.exit(1)

if __name__ == '__main__':
    main()

