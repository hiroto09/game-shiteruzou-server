FROM python:3.10-slim

# 作業ディレクトリ
WORKDIR /app

# 必要なライブラリをインストール
RUN pip install --no-cache-dir fastapi uvicorn slack_bolt python-dotenv

# アプリコードをコピー
COPY main.py /app/main.py

# uvicorn で起動 (修正: server → main)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
