"""
設定管理モジュール
環境変数から各APIの認証情報を読み込む
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """アプリケーション設定"""
    
    # Zoom API設定
    zoom_api_key: str = Field(..., env="ZOOM_API_KEY")
    zoom_api_secret: str = Field(..., env="ZOOM_API_SECRET")
    zoom_account_id: Optional[str] = Field(None, env="ZOOM_ACCOUNT_ID")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 設定値の空白を除去
        if hasattr(self, 'zoom_api_key') and self.zoom_api_key:
            self.zoom_api_key = self.zoom_api_key.strip()
        if hasattr(self, 'zoom_api_secret') and self.zoom_api_secret:
            self.zoom_api_secret = self.zoom_api_secret.strip()
        if hasattr(self, 'zoom_account_id') and self.zoom_account_id:
            self.zoom_account_id = self.zoom_account_id.strip()
    
    # Gemini API設定
    gemini_api_key: str = Field(..., env="GEMINI_API_KEY")
    gemini_model_name: str = Field(
        default="gemini-2.5-pro", 
        env="GEMINI_MODEL_NAME",
        description="使用するGeminiモデル名。デフォルト: gemini-2.5-pro（1日5回程度の使用に最適、高精度）"
    )
    
    # Chatwork API設定
    chatwork_api_token: str = Field(..., env="CHATWORK_API_TOKEN")
    default_chatwork_room_id: Optional[str] = Field(None, env="DEFAULT_CHATWORK_ROOM_ID")
    
    # 一時ファイル保存先
    temp_dir: str = Field(default="./temp", env="TEMP_DIR")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    @classmethod
    def get_env_file_path(cls):
        """環境変数ファイルのパスを取得（絶対パス）"""
        import os
        from pathlib import Path
        # プロジェクトルートを探す（config.pyがあるディレクトリ）
        config_dir = Path(__file__).parent.absolute()
        env_file = config_dir / ".env"
        return str(env_file)


def get_settings() -> Settings:
    """設定インスタンスを取得"""
    import os
    from pathlib import Path
    # プロジェクトルートを探す（config.pyがあるディレクトリ）
    config_dir = Path(__file__).parent.absolute()
    env_file = config_dir / ".env"
    
    # 環境変数に.envファイルのパスを設定（os.chdirを使わない方法）
    # これによりブロッキングを回避
    original_env_file = os.environ.get("ENV_FILE")
    try:
        if env_file.exists():
            os.environ["ENV_FILE"] = str(env_file)
        # 作業ディレクトリを一時的に変更して.envファイルを読み込む
        original_cwd = os.getcwd()
        try:
            os.chdir(config_dir)
            return Settings()
        finally:
            os.chdir(original_cwd)
    finally:
        # 環境変数を復元
        if original_env_file:
            os.environ["ENV_FILE"] = original_env_file
        elif "ENV_FILE" in os.environ:
            del os.environ["ENV_FILE"]

