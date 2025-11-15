"""
Gemini API使用状況の追跡モジュール
1日の使用回数をカウントして制限を監視
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class UsageTracker:
    """API使用状況の追跡"""
    
    USAGE_FILE = "gemini_usage.json"
    
    # モデルごとの1日の制限
    DAILY_LIMITS = {
        "gemini-2.5-pro": 100,
        "gemini-2.5-flash-exp": 1500,
        "gemini-2.0-flash-exp": 1500,
        "gemini-1.5-pro": 1500,
        "gemini-1.5-flash": 1500,
    }
    
    def __init__(self):
        self.usage_file = Path(self.USAGE_FILE)
        self.usage_data: Dict = {}
        self.load_usage()
    
    def load_usage(self):
        """使用状況を読み込む"""
        if self.usage_file.exists():
            try:
                with open(self.usage_file, "r", encoding="utf-8") as f:
                    self.usage_data = json.load(f)
            except Exception as e:
                logger.error(f"使用状況ファイルの読み込みに失敗: {e}")
                self.usage_data = {}
        else:
            self.usage_data = {}
    
    def save_usage(self):
        """使用状況を保存"""
        try:
            with open(self.usage_file, "w", encoding="utf-8") as f:
                json.dump(self.usage_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"使用状況ファイルの保存に失敗: {e}")
    
    def get_today_key(self, model_name: str) -> str:
        """今日の日付をキーとして取得"""
        today = datetime.now().strftime("%Y-%m-%d")
        return f"{model_name}_{today}"
    
    def can_use(self, model_name: str):
        """
        使用可能かどうかを確認
        
        Returns:
            (使用可能か, 今日の使用回数, 制限回数)
        """
        limit = self.DAILY_LIMITS.get(model_name, 100)
        key = self.get_today_key(model_name)
        
        today_count = self.usage_data.get(key, 0)
        can_use = today_count < limit
        
        return can_use, today_count, limit
    
    def record_usage(self, model_name: str):
        """使用回数を記録"""
        key = self.get_today_key(model_name)
        current_count = self.usage_data.get(key, 0)
        self.usage_data[key] = current_count + 1
        
        # 古いデータを削除（30日以上前）
        cutoff_date = datetime.now() - timedelta(days=30)
        keys_to_delete = []
        for k in self.usage_data.keys():
            if model_name in k:
                date_str = k.split("_")[-1]
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    if date_obj < cutoff_date:
                        keys_to_delete.append(k)
                except ValueError:
                    pass
        
        for k in keys_to_delete:
            if k in self.usage_data:
                del self.usage_data[k]
        
        self.save_usage()
        
        # 警告を表示
        can_use, count, limit = self.can_use(model_name)
        if count >= limit * 0.8:  # 80%以上使用したら警告
            logger.warning(
                f"⚠️  Gemini API使用状況: {count}/{limit}回使用済み（{model_name}）"
            )
        elif not can_use:
            logger.error(
                f"❌ Gemini API使用制限に達しました: {count}/{limit}回（{model_name}）"
            )
    
    def get_usage_summary(self, model_name: str) -> Dict:
        """使用状況のサマリーを取得"""
        can_use, count, limit = self.can_use(model_name)
        return {
            "model": model_name,
            "today_count": count,
            "limit": limit,
            "remaining": max(0, limit - count),
            "can_use": can_use,
            "usage_percentage": (count / limit * 100) if limit > 0 else 0
        }

