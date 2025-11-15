FROM python:3.11-slim

WORKDIR /app

# システムの依存関係をインストール
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Pythonの依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# 一時ディレクトリを作成
RUN mkdir -p temp

# ポートを公開
EXPOSE 8000

# アプリケーションを起動
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]


