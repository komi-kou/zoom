"""
Gemini API連携モジュール
音声・動画ファイルから文字起こしと議事録生成を行う
"""
import os
import time
import google.generativeai as genai
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class GeminiClient:
    """Gemini APIクライアント"""
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-pro"):
        """
        Gemini APIクライアントを初期化
        
        Args:
            api_key: Gemini APIキー
            model_name: 使用するモデル名（デフォルト: gemini-2.5-pro）
                       
                       推奨モデル（1日5回程度の使用）:
                       - gemini-2.5-pro: デフォルト（1日100回無料、最高精度、1日5回なら余裕）
                       - gemini-1.5-flash: コスト重視（1日1,500回無料、コスト効率が良い）
                       
                       大量使用の場合:
                       - gemini-2.0-flash-exp: 自動処理に最適（1日1,500回無料、高速）
                       - gemini-1.5-pro: バランス型（1日1,500回無料、中程度のコスト）
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.model_name = model_name
        
        # 使用状況追跡を初期化（オプション）
        try:
            from usage_tracker import UsageTracker
            self.usage_tracker = UsageTracker()
        except ImportError:
            self.usage_tracker = None
            logger.warning("usage_trackerモジュールが見つかりません。使用状況の追跡をスキップします。")
        
        # モデルごとの制限を警告
        if "2.5-pro" in model_name.lower():
            logger.warning(
                "⚠️  Gemini 2.5 Proは1日100回の制限があります。"
                "自動処理で大量に使う場合は、gemini-2.0-flash-expまたはgemini-1.5-flashを推奨します。"
            )
        
        # 使用可能かどうかを確認（警告のみ、エラーにはしない）
        if self.usage_tracker:
            try:
                can_use, count, limit = self.usage_tracker.can_use(model_name)
                if not can_use:
                    logger.warning(
                        f"⚠️ Gemini APIの使用制限に達している可能性があります: {count}/{limit}回（{model_name}）。"
                        "実際のAPI呼び出しで確認します。"
                    )
                else:
                    logger.info(f"Gemini API使用状況: {count}/{limit}回使用済み（{model_name}）")
            except Exception as e:
                # usage_trackerのエラーは無視（実際のAPI呼び出しで確認）
                logger.warning(f"使用状況の確認に失敗しました（無視します）: {e}")
    
    def summarize_transcript(self, transcript_text: str) -> str:
        """
        文字起こしテキストから議事録を生成
        
        Args:
            transcript_text: 文字起こしテキスト
            
        Returns:
            議事録テキスト
        """
        prompt = """以下の会議の文字起こしを読み、構造化された議事録を作成してください。

議事録の形式（Markdown記法は使用せず、プレーンテキストで記載してください）：

会議概要
[会議の目的と主要なトピックを1-2文で要約]

主な議論内容
[重要な議論ポイントを箇条書きで整理]
- 議論ポイント1
- 議論ポイント2
...

決定事項
- [決定事項1]
- [決定事項2]
...

ToDo
[担当者名] [タスク内容] [期限]
[担当者名] [タスク内容] [期限]
...

その他
[その他の重要な情報]

注意事項：
- 見出しには「##」や「###」などのMarkdown記法は使用しないでください
- 強調には「**」などのMarkdown記法は使用しないでください
- アクションアイテムは「ToDo」セクションに記載してください
- すべてプレーンテキストで記載してください
"""
        
        try:
            response = self.model.generate_content(f"{prompt}\n\n{transcript_text}")
            
            # 使用回数を記録
            if self.usage_tracker:
                self.usage_tracker.record_usage(self.model_name)
            
            return response.text
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            
            # クォータ制限エラーの場合、詳細な情報を提供
            if "429" in error_msg or "ResourceExhausted" in error_type or "quota" in error_msg.lower():
                logger.warning(f"Gemini APIクォータ制限エラー: {error_msg[:300]}")
                # クォータ制限の場合は、少し待ってからリトライを提案
                import re
                retry_match = re.search(r'retry.*?(\d+)', error_msg, re.IGNORECASE)
                if retry_match:
                    retry_seconds = int(retry_match.group(1))
                    logger.info(f"約{retry_seconds}秒後に再試行可能です")
                raise Exception(f"Gemini APIのクォータ制限に達しています。\n\n"
                              f"エラー詳細: {error_msg[:200]}\n\n"
                              f"【対処方法】\n"
                              f"1. しばらく待ってから再度試してください（1分間に2回のリクエスト制限）\n"
                              f"2. 別のGeminiモデル（gemini-1.5-flashなど）を試してください\n"
                              f"3. Google AI Studioで使用状況を確認してください")
            else:
                logger.error(f"Gemini APIエラー: {e}")
                raise
    
    def transcribe_and_summarize(self, video_file_path: str, language: str = "ja") -> str:
        """
        動画ファイルから文字起こしと議事録を生成
        
        Args:
            video_file_path: 動画ファイルのパス
            language: 言語コード（デフォルト: ja）
            
        Returns:
            議事録テキスト
        """
        if not os.path.exists(video_file_path):
            raise FileNotFoundError(f"ファイルが見つかりません: {video_file_path}")
        
        # ファイルをアップロード
        file = genai.upload_file(path=video_file_path)
        
        # ファイルのアップロード完了を待つ
        while file.state.name == "PROCESSING":
            time.sleep(2)
            file = genai.get_file(file.name)
        
        if file.state.name == "FAILED":
            raise Exception(f"ファイルのアップロードに失敗しました: {file.state.name}")
        
        try:
            # プロンプトを設定
            prompt = f"""
以下の動画ファイルから会議の議事録を作成してください。

要件:
1. 会議の主要な議題・トピックを抽出
2. 各トピックごとに議論の内容を要約
3. 決定事項やToDoを明確に記載
4. 参加者の発言内容を適切に整理
5. 日本語で読みやすい形式で出力
6. Markdown記法（##、###、**など）は使用せず、プレーンテキストで記載

議事録の形式:

会議議事録

日時
[会議の日時]

参加者
[参加者リスト（可能な場合）]

議題
1. [議題1]
2. [議題2]
...

議論内容
[議題1]
[議論の要約]

[議題2]
[議論の要約]
...

決定事項
- [決定事項1]
- [決定事項2]
...

ToDo
[担当者名] [タスク内容] [期限]
[担当者名] [タスク内容] [期限]
...

その他
[その他の重要な情報]

注意事項：
- 見出しには「##」や「###」などのMarkdown記法は使用しないでください
- 強調には「**」などのMarkdown記法は使用しないでください
- アクションアイテムは「ToDo」セクションに記載してください
- すべてプレーンテキストで記載してください
"""
            
            # モデルに送信
            response = self.model.generate_content([prompt, file])
            
            # 使用回数を記録
            if self.usage_tracker:
                self.usage_tracker.record_usage(self.model_name)
            
            return response.text
            
        finally:
            # アップロードしたファイルを削除
            try:
                genai.delete_file(file.name)
            except Exception:
                pass
    
    def transcribe_audio(self, audio_file_path: str, language: str = "ja") -> str:
        """
        音声ファイルから文字起こしと議事録を生成
        
        Args:
            audio_file_path: 音声ファイルのパス
            language: 言語コード（デフォルト: ja）
            
        Returns:
            議事録テキスト
        """
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"ファイルが見つかりません: {audio_file_path}")
        
        # ファイルをアップロード
        file = genai.upload_file(path=audio_file_path)
        
        # ファイルのアップロード完了を待つ
        while file.state.name == "PROCESSING":
            time.sleep(2)
            file = genai.get_file(file.name)
        
        if file.state.name == "FAILED":
            raise Exception(f"ファイルのアップロードに失敗しました: {file.state.name}")
        
        try:
            # プロンプトを設定
            prompt = f"""
以下の音声ファイルから会議の議事録を作成してください。

要件:
1. 会議の主要な議題・トピックを抽出
2. 各トピックごとに議論の内容を要約
3. 決定事項やToDoを明確に記載
4. 参加者の発言内容を適切に整理
5. 日本語で読みやすい形式で出力
6. Markdown記法（##、###、**など）は使用せず、プレーンテキストで記載

議事録の形式:

会議議事録

日時
[会議の日時]

参加者
[参加者リスト（可能な場合）]

議題
1. [議題1]
2. [議題2]
...

議論内容
[議題1]
[議論の要約]

[議題2]
[議論の要約]
...

決定事項
- [決定事項1]
- [決定事項2]
...

ToDo
[担当者名] [タスク内容] [期限]
[担当者名] [タスク内容] [期限]
...

その他
[その他の重要な情報]

注意事項：
- 見出しには「##」や「###」などのMarkdown記法は使用しないでください
- 強調には「**」などのMarkdown記法は使用しないでください
- アクションアイテムは「ToDo」セクションに記載してください
- すべてプレーンテキストで記載してください
"""
            
            # モデルに送信
            response = self.model.generate_content([prompt, file])
            
            # 使用回数を記録
            if self.usage_tracker:
                self.usage_tracker.record_usage(self.model_name)
            
            return response.text
            
        finally:
            # アップロードしたファイルを削除
            try:
                genai.delete_file(file.name)
            except Exception:
                pass

