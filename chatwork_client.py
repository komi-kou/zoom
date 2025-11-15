"""
Chatwork API連携モジュール
トークルームへのメッセージ送信を行う
"""
import requests
from typing import Optional


class ChatworkClient:
    """Chatwork APIクライアント"""
    
    BASE_URL = "https://api.chatwork.com/v2"
    MAX_MESSAGE_LENGTH = 20000  # Chatworkのメッセージ文字数制限（安全のため少し小さめに設定）
    
    def __init__(self, api_token: str):
        """
        Chatwork APIクライアントを初期化
        
        Args:
            api_token: Chatwork APIトークン
        """
        self.api_token = api_token
    
    def _get_headers(self) -> dict:
        """
        APIリクエスト用のヘッダーを取得
        
        Returns:
            ヘッダー辞書
        """
        return {
            "X-ChatWorkToken": self.api_token,
            "Content-Type": "application/x-www-form-urlencoded"
        }
    
    def send_message(self, room_id: str, message: str) -> dict:
        """
        トークルームにメッセージを送信
        
        Args:
            room_id: ルームID
            message: 送信するメッセージ
            
        Returns:
            レスポンスデータ
        """
        url = f"{self.BASE_URL}/rooms/{room_id}/messages"
        headers = self._get_headers()
        
        # メッセージが長い場合は分割
        if len(message) > self.MAX_MESSAGE_LENGTH:
            messages = self._split_message(message)
            results = []
            for msg in messages:
                data = {"body": msg}
                response = requests.post(url, headers=headers, data=data)
                response.raise_for_status()
                results.append(response.json())
            return results
        else:
            data = {"body": message}
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()
            return response.json()
    
    def _split_message(self, message: str) -> list:
        """
        長いメッセージを適切なサイズに分割
        
        Args:
            message: 分割するメッセージ
            
        Returns:
            分割されたメッセージのリスト
        """
        messages = []
        current_message = ""
        
        # 改行で分割して、可能な限り段落を保持
        paragraphs = message.split("\n")
        
        for paragraph in paragraphs:
            # 段落を追加した場合の長さを確認
            test_message = current_message + paragraph + "\n"
            
            if len(test_message) > self.MAX_MESSAGE_LENGTH:
                # 現在のメッセージを保存
                if current_message:
                    messages.append(current_message.strip())
                current_message = paragraph + "\n"
            else:
                current_message = test_message
        
        # 残りのメッセージを追加
        if current_message:
            messages.append(current_message.strip())
        
        return messages
    
    def get_room_info(self, room_id: str) -> dict:
        """
        ルーム情報を取得
        
        Args:
            room_id: ルームID
            
        Returns:
            ルーム情報
        """
        url = f"{self.BASE_URL}/rooms/{room_id}"
        headers = self._get_headers()
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        return response.json()
    
    def get_my_info(self) -> dict:
        """
        自分の情報を取得（API接続テスト用）
        
        Returns:
            自分の情報（アカウントID、名前など）
        """
        url = f"{self.BASE_URL}/me"
        headers = self._get_headers()
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        return response.json()
    
    def test_connection(self) -> dict:
        """
        API接続をテスト
        
        Returns:
            テスト結果（成功時は自分の情報を含む）
            
        Raises:
            requests.exceptions.RequestException: API接続エラー
        """
        try:
            my_info = self.get_my_info()
            return {
                "success": True,
                "account_id": my_info.get("account_id"),
                "name": my_info.get("name"),
                "email": my_info.get("email")
            }
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise ValueError("APIトークンが無効です。正しいAPIトークンを設定してください。")
            elif e.response.status_code == 403:
                raise ValueError("APIトークンに権限がありません。")
            else:
                raise ValueError(f"API接続エラー: {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            raise ValueError(f"ネットワークエラー: {str(e)}")


