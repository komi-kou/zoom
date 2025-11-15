"""
自動処理設定管理モジュール
ミーティングIDとChatworkルームIDのマッピング、処理済み状態を管理
（Webhook方式で使用）
"""
import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class AutoProcessConfig:
    """自動処理設定管理"""
    
    CONFIG_FILE = "auto_process_config.json"
    
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
    
    def load_config(self):
        """設定を読み込む"""
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            else:
                self.config = {}
        except Exception as e:
            logger.warning(f"設定ファイルの読み込みに失敗（初回起動時は正常）: {e}")
            self.config = {}
    
    def save_config(self):
        """設定を保存"""
        try:
            # ディレクトリが存在しない場合は作成
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"設定ファイルの保存に失敗: {e}")
            # Vercelでは/tmpディレクトリへの書き込みが失敗する可能性があるため、エラーを無視しない
    
    def add_mapping(self, meeting_id: str, room_id: str, meeting_topic: Optional[str] = None):
        """
        ミーティングIDとChatworkルームIDのマッピングを追加
        
        Args:
            meeting_id: ZoomミーティングID
            room_id: ChatworkルームID
            meeting_topic: ミーティングトピック（オプション）
        """
        self.config[meeting_id] = {
            "room_id": room_id,
            "meeting_topic": meeting_topic,
            "created_at": datetime.now().isoformat(),
            "processed": False
        }
        self.save_config()
    
    def remove_mapping(self, meeting_id: str):
        """マッピングを削除"""
        if meeting_id in self.config:
            del self.config[meeting_id]
            self.save_config()
    
    def get_room_id(self, meeting_id: str) -> Optional[str]:
        """ミーティングIDに対応するルームIDを取得"""
        if meeting_id in self.config:
            return self.config[meeting_id].get("room_id")
        return None
    
    def mark_as_processed(self, meeting_id: str):
        """処理済みマーク"""
        if meeting_id in self.config:
            self.config[meeting_id]["processed"] = True
            self.config[meeting_id]["processed_at"] = datetime.now().isoformat()
            self.save_config()
    
    def is_processed(self, meeting_id: str) -> bool:
        """処理済みかどうか確認"""
        if meeting_id in self.config:
            return self.config[meeting_id].get("processed", False)
        return False
    
    def get_all_mappings(self) -> Dict[str, Dict]:
        """すべてのマッピングを取得"""
        return self.config.copy()
    
    def get_pending_meetings(self) -> List[str]:
        """未処理のミーティングIDリストを取得"""
        return [
            meeting_id 
            for meeting_id, config in self.config.items()
            if not config.get("processed", False)
        ]


# Schedulerクラスは削除しました（Webhook方式のみを使用するため不要）

