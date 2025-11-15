"""
Zoom API連携モジュール
録画ファイルの取得とダウンロードを行う
"""
import os
import time
import requests
import jwt
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ZoomClient:
    """Zoom APIクライアント"""
    
    BASE_URL = "https://api.zoom.us/v2"
    
    def __init__(self, api_key: str, api_secret: str, account_id: Optional[str] = None):
        """
        Zoom APIクライアントを初期化
        
        Args:
            api_key: Zoom APIキー
            api_secret: Zoom APIシークレット
            account_id: ZoomアカウントID（Server-to-Server OAuth使用時）
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.account_id = account_id
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
    
    def _generate_jwt_token(self) -> str:
        """
        JWTトークンを生成
        
        Returns:
            JWTトークン文字列
        """
        payload = {
            "iss": self.api_key,
            "exp": int(time.time()) + 3600  # 1時間有効
        }
        token = jwt.encode(payload, self.api_secret, algorithm="HS256")
        return token
    
    def _get_access_token(self) -> str:
        """
        OAuthアクセストークンを取得（Server-to-Server OAuth使用時）
        
        Returns:
            アクセストークン
        """
        if self.account_id is None:
            raise ValueError("account_idが必要です（Server-to-Server OAuth使用時）")
        
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.access_token
        
        # 認証情報の検証
        if not self.api_key or not self.api_secret:
            raise ValueError("API Key（Client ID）とAPI Secret（Client Secret）が設定されていません")
        
        # 空白や改行を除去
        api_key = self.api_key.strip()
        api_secret = self.api_secret.strip()
        account_id = self.account_id.strip()
        
        if not api_key or not api_secret or not account_id:
            raise ValueError("API Key、API Secret、Account IDが正しく設定されていません")
        
        # デバッグ情報（実際の値の長さと最初の数文字のみ表示）
        logger.info(f"API Key長: {len(api_key)}, 最初の5文字: {api_key[:5] if len(api_key) >= 5 else api_key}")
        logger.info(f"API Secret長: {len(api_secret)}, 最初の5文字: {api_secret[:5] if len(api_secret) >= 5 else api_secret}")
        logger.info(f"Account ID: {account_id}")
        
        url = "https://zoom.us/oauth/token"
        
        # Server-to-Server OAuthでは、パラメータをリクエストボディとして送信
        data = {
            "grant_type": "account_credentials",
            "account_id": account_id
        }
        
        # Basic認証: requestsライブラリのauthパラメータを使用（自動的にBase64エンコード）
        # これが以前動作していた方法です
        auth = (api_key, api_secret)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            logger.info(f"リクエスト送信: URL={url}, grant_type=account_credentials, account_id={account_id}")
            response = requests.post(url, data=data, auth=auth, headers=headers, timeout=10)
            logger.info(f"レスポンスステータス: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"レスポンス本文: {response.text[:500]}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Zoom APIへの接続に失敗: {str(e)}")
            raise requests.exceptions.RequestException(f"Zoom APIへの接続に失敗しました: {str(e)}")
        
        # エラーレスポンスの詳細を確認
        if response.status_code != 200:
            error_detail = ""
            try:
                error_json = response.json()
                error_reason = error_json.get('reason', '')
                error_description = error_json.get('error_description', '')
                error_detail = f" - {error_reason or error_description or 'Unknown error'}"
                
                # より詳細なエラーメッセージを構築
                if 'Invalid client_id or client_secret' in str(error_json):
                    error_detail += "\n\n【確認事項】\n" \
                                  "1. Zoom Marketplaceの「App Credentials」セクションで、Client IDとClient Secretが正しくコピーされているか確認してください\n" \
                                  "2. Client Secretは「Show」ボタンをクリックして表示された値をコピーしてください\n" \
                                  "3. 設定値に余分な空白や改行が含まれていないか確認してください\n" \
                                  "4. アプリが「Activated」状態になっているか確認してください"
            except:
                error_detail = f" - {response.text[:200]}"
            
            raise requests.exceptions.HTTPError(
                f"{response.status_code} Client Error: {response.reason} for url: {response.url}{error_detail}"
            )
        
        response.raise_for_status()
        
        token_data = response.json()
        self.access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)  # 1分前に更新
        
        return self.access_token
    
    def _get_headers(self, force_oauth: bool = False) -> Dict[str, str]:
        """
        APIリクエスト用のヘッダーを取得
        
        Args:
            force_oauth: Trueの場合、強制的にOAuthを使用（デフォルト: False）
                         Falseの場合、JWT認証を優先的に試す
        
        Returns:
            ヘッダー辞書
        """
        # 以前動作していた方法: JWT認証を優先的に試す
        # Account IDが設定されていても、まずJWT認証を試す
        if not force_oauth:
            # JWT認証を試す（以前動作していた方法）
            token = self._generate_jwt_token()
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        
        # OAuth使用時（force_oauthがTrueの場合、またはJWT認証が失敗した場合に呼び出される）
        if self.account_id:
            token = self._get_access_token()
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        else:
            # account_idがない場合は、JWT認証を使用
            token = self._generate_jwt_token()
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
    
    def get_meeting_recordings(self, meeting_id: str) -> List[Dict]:
        """
        ミーティングの録画情報を取得
        
        Args:
            meeting_id: ミーティングID
            
        Returns:
            録画情報のリスト
        """
        url = f"{self.BASE_URL}/meetings/{meeting_id}/recordings"
        
        # まずJWT認証を試す（以前動作していた方法）
        headers = self._get_headers(force_oauth=False)
        response = requests.get(url, headers=headers)
        
        # JWT認証が失敗した場合（401エラー）、OAuthを試す
        if response.status_code == 401 and self.account_id:
            logger.info("JWT認証が失敗したため、Server-to-Server OAuthを試します")
            headers = self._get_headers(force_oauth=True)
            response = requests.get(url, headers=headers)
        
        response.raise_for_status()
        
        data = response.json()
        return data.get("recording_files", [])
    
    def download_recording(self, download_url: str, file_path: str) -> str:
        """
        録画ファイルをダウンロード
        
        Args:
            download_url: ダウンロードURL
            file_path: 保存先ファイルパス
            
        Returns:
            保存されたファイルパス
        """
        # Zoom APIの録画ダウンロードURLは、通常のAPIエンドポイントとは異なる認証が必要
        # ダウンロードURLには既に認証情報が含まれている場合と、ヘッダー認証が必要な場合がある
        # 401エラーが発生する場合は、OAuthトークンを使用する必要がある可能性がある
        
        # まず、OAuthトークンを取得してヘッダーに設定
        headers = self._get_headers(force_oauth=True)
        
        # ダウンロードURLにアクセストークンが含まれていない場合は、ヘッダーで認証
        # URLにaccess_tokenが含まれている場合は、そのまま使用
        if "access_token" not in download_url:
            # ヘッダー認証を使用（OAuthトークンを使用）
            # ダウンロードURLは通常のAPIエンドポイントとは異なるため、Content-Typeを削除
            download_headers = {
                "Authorization": headers.get("Authorization", ""),
            }
            response = requests.get(download_url, headers=download_headers, stream=True, timeout=300)
        else:
            # URLにトークンが含まれている場合は、ヘッダーなしでアクセス
            response = requests.get(download_url, stream=True, timeout=300)
        
        # 401エラーの場合は、JWT認証を試す
        if response.status_code == 401:
            logger.warning("OAuth認証が失敗したため、JWT認証を試します")
            jwt_headers = self._get_headers(force_oauth=False)
            download_headers = {
                "Authorization": jwt_headers.get("Authorization", ""),
            }
            response = requests.get(download_url, headers=download_headers, stream=True, timeout=300)
        
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return file_path
    
    def get_transcript(self, meeting_id: str) -> Optional[str]:
        """
        ミーティングの文字起こしを取得
        
        Args:
            meeting_id: ミーティングID
            
        Returns:
            文字起こしテキスト（見つからない場合はNone）
        """
        recordings = self.get_meeting_recordings(meeting_id)
        
        if not recordings:
            return None
        
        # 文字起こしファイルを探す（TRANSCRIPT, VTT, TXT形式）
        transcript_recording = None
        for recording in recordings:
            file_type = recording.get("file_type", "").upper()
            if file_type in ["TRANSCRIPT", "VTT", "TXT"] and recording.get("status") == "completed":
                transcript_recording = recording
                break
        
        if not transcript_recording:
            return None
        
        download_url = transcript_recording.get("download_url")
        if not download_url:
            return None
        
        # 文字起こしをダウンロード
        headers = self._get_headers()
        if "access_token" not in download_url:
            response = requests.get(download_url, headers=headers)
        else:
            response = requests.get(download_url)
        
        response.raise_for_status()
        
        # テキストとして取得
        transcript_text = response.text
        
        # VTT形式の場合は、タイムスタンプを除去してテキストのみ抽出
        if transcript_recording.get("file_type", "").upper() == "VTT":
            lines = transcript_text.split('\n')
            text_lines = []
            for line in lines:
                line = line.strip()
                # VTTのタイムスタンプ行や空行をスキップ
                if not line or line.startswith('WEBVTT') or '-->' in line or line.isdigit():
                    continue
                text_lines.append(line)
            transcript_text = '\n'.join(text_lines)
        
        return transcript_text
    
    def get_recording_file(self, meeting_id: str, output_dir: str) -> Optional[str]:
        """
        ミーティングの録画ファイルを取得してダウンロード
        
        Args:
            meeting_id: ミーティングID
            output_dir: 保存先ディレクトリ
            
        Returns:
            ダウンロードしたファイルパス（見つからない場合はNone）
        """
        recordings = self.get_meeting_recordings(meeting_id)
        
        if not recordings:
            return None
        
        # 録画ファイルを取得（優先順位: M4A > MP4 > その他）
        # M4A音声ファイルの方が小さいため、Gemini APIのトークン制限に引っかかりにくい
        video_recording = None
        
        # まずM4A音声ファイルを探す（ファイルサイズが小さいため優先）
        for recording in recordings:
            if recording.get("file_type") == "M4A" and recording.get("status") == "completed":
                video_recording = recording
                break
        
        # M4Aが見つからない場合はMP4を探す
        if not video_recording:
            for recording in recordings:
                if recording.get("file_type") == "MP4" and recording.get("status") == "completed":
                    video_recording = recording
                    break
        
        # MP4も見つからない場合は最初の完了した録画を使用
        if not video_recording:
            for recording in recordings:
                if recording.get("status") == "completed":
                    video_recording = recording
                    break
        
        if not video_recording:
            return None
        
        download_url = video_recording.get("download_url")
        if not download_url:
            return None
        
        # ファイル名を生成
        file_extension = video_recording.get("file_extension", "mp4")
        file_name = f"{meeting_id}_{video_recording.get('id', 'recording')}.{file_extension}"
        file_path = os.path.join(output_dir, file_name)
        
        # ダウンロード
        self.download_recording(download_url, file_path)
        
        return file_path
    
    def list_meetings(self, user_id: str = "me", page_size: int = 30, from_date: Optional[str] = None, to_date: Optional[str] = None) -> Dict:
        """
        ミーティング一覧を取得
        
        Args:
            user_id: ユーザーID（デフォルト: "me"）
            page_size: 1ページあたりの件数（最大300）
            from_date: 開始日時（YYYY-MM-DD形式、Noneの場合は期間制限なし）
            to_date: 終了日時（YYYY-MM-DD形式）
            
        Returns:
            ミーティング一覧
        """
        url = f"{self.BASE_URL}/users/{user_id}/meetings"
        
        # まずJWT認証を試す（以前動作していた方法）
        headers = self._get_headers(force_oauth=False)
        params = {
            "page_size": min(page_size, 300),  # Zoom APIの最大値は300
            "type": "past"  # 過去のミーティングを取得
        }
        
        # from_dateが指定されている場合のみ追加
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        
        response = requests.get(url, headers=headers, params=params)
        
        # JWT認証が失敗した場合（401エラー）、OAuthを試す
        if response.status_code == 401 and self.account_id:
            logger.info("JWT認証が失敗したため、Server-to-Server OAuthを試します")
            headers = self._get_headers(force_oauth=True)
            response = requests.get(url, headers=headers, params=params)
        
        response.raise_for_status()
        
        return response.json()
    
    def get_recent_meetings_with_recordings(self, hours: Optional[int] = 24, include_without_recordings: bool = False) -> List[Dict]:
        """
        最近終了した録画付きミーティングを取得
        
        Args:
            hours: 何時間前までのミーティングを取得するか（Noneの場合は期間制限なし）
            include_without_recordings: Trueの場合、録画がないミーティングも含める（デフォルト: False）
            
        Returns:
            録画付きミーティングのリスト（include_without_recordings=Trueの場合は録画がないものも含む）
        """
        # hoursがNoneの場合は期間制限なし（from_dateを指定しない）
        if hours is None:
            # 期間制限なしで全ての過去ミーティングを取得
            # Zoom APIの制限により、ページネーションで全て取得する必要がある
            meetings_data = self.list_meetings(page_size=300)  # 最大300件まで
        else:
            from_date = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d")
            meetings_data = self.list_meetings(from_date=from_date, page_size=300)
        
        meetings = meetings_data.get("meetings", [])
        
        # 録画情報の取得を並列化して高速化
        # 大量のミーティングがある場合は時間がかかるため、並列処理で高速化
        meetings_with_recordings = []
        
        # 並列処理で録画情報を取得（最大10スレッド）
        import concurrent.futures
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def get_recording_info(meeting):
            """ミーティングの録画情報を取得"""
            meeting_id = str(meeting.get("id"))
            try:
                recordings = self.get_meeting_recordings(meeting_id)
                if recordings:
                    # 完了した録画があるか確認
                    completed_recordings = [
                        r for r in recordings 
                        if r.get("status") == "completed"
                    ]
                    if completed_recordings:
                        meeting["recordings"] = completed_recordings
                        return meeting, True
                    elif include_without_recordings:
                        # 録画がないが、include_without_recordingsがTrueの場合は含める
                        meeting["recordings"] = []
                        return meeting, True
                elif include_without_recordings:
                    # 録画がないが、include_without_recordingsがTrueの場合は含める
                    meeting["recordings"] = []
                    return meeting, True
                return None, False
            except Exception as e:
                # 録画がない場合（404エラーなど）
                if include_without_recordings:
                    # 録画がないが、include_without_recordingsがTrueの場合は含める
                    meeting["recordings"] = []
                    # エラーメッセージを短縮（長すぎるとJSONが大きくなりすぎる）
                    error_msg = str(e)
                    if len(error_msg) > 100:
                        error_msg = error_msg[:100] + "..."
                    meeting["recording_error"] = error_msg
                    return meeting, True
                return None, False
        
        # 並列処理で録画情報を取得（最大10スレッド）
        with ThreadPoolExecutor(max_workers=10) as executor:
            # 全てのミーティングに対して録画情報の取得を開始
            future_to_meeting = {
                executor.submit(get_recording_info, meeting): meeting 
                for meeting in meetings
            }
            
            # 完了したタスクから順に処理
            for future in as_completed(future_to_meeting):
                try:
                    meeting, should_include = future.result(timeout=5.0)  # 各ミーティングのタイムアウトは5秒
                    if should_include and meeting:
                        meetings_with_recordings.append(meeting)
                except concurrent.futures.TimeoutError:
                    # 個別のミーティングのタイムアウトは無視して続行
                    meeting = future_to_meeting[future]
                    if include_without_recordings:
                        meeting["recordings"] = []
                        meeting["recording_error"] = "タイムアウト"
                        meetings_with_recordings.append(meeting)
                except Exception as e:
                    # その他のエラーも無視して続行
                    meeting = future_to_meeting[future]
                    if include_without_recordings:
                        meeting["recordings"] = []
                        error_msg = str(e)
                        if len(error_msg) > 100:
                            error_msg = error_msg[:100] + "..."
                        meeting["recording_error"] = error_msg
                        meetings_with_recordings.append(meeting)
        
        return meetings_with_recordings

