FROM python:3.10-slim

# 作業ディレクトリ
WORKDIR /app

# 必要なライブラリをインストール
RUN pip install --no-cache-dir fastapi uvicorn slack_bolt slack_sdk python-dotenv mysql-connector-python

# アプリコードをコピー
COPY main.py /app/main.py

# uvicorn で起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
