"""
ローカル開発サーバー起動スクリプト
"""
import uvicorn
import os

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"\n{'='*60}")
    print("🚀 Zoom議事録自動生成ツール - ローカルサーバー起動中...")
    print(f"{'='*60}\n")
    print(f"📱 ブラウザで以下のURLにアクセスしてください:")
    print(f"   http://localhost:{port}")
    print(f"\n💡 停止する場合は Ctrl+C を押してください\n")
    print(f"{'='*60}\n")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_excludes=["venv/*", "*.pyc", "__pycache__/*", ".git/*", "temp/*"],
        log_level="info"
    )


