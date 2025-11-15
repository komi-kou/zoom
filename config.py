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
    # Zoom Webhook Secret Token（Challenge-response検証と通常のWebhookイベントの署名検証に使用）
    zoom_webhook_secret_token: Optional[str] = Field(None, env="ZOOM_WEBHOOK_SECRET_TOKEN")
    
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
        # Vercelなどのサーバーレス環境では環境変数から直接読み込む
        # .envファイルはローカル開発時のみ使用（存在する場合のみ）
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
    
    # Vercelなどのサーバーレス環境では環境変数から直接読み込む
    # .envファイルはローカル開発時のみ使用
    try:
        # まず環境変数から直接読み込む（Vercelではこれが正しい方法）
        settings = Settings()
        return settings
    except Exception as e:
        # 環境変数から読み込めない場合、.envファイルを試す（ローカル開発用）
        config_dir = Path(__file__).parent.absolute()
        env_file = config_dir / ".env"
        
        if env_file.exists():
            # .envファイルが存在する場合のみ、作業ディレクトリを変更して読み込む
            original_cwd = os.getcwd()
            try:
                os.chdir(config_dir)
                return Settings()
            finally:
                os.chdir(original_cwd)
        else:
            # .envファイルも存在しない場合はエラーを再発生
            raise

