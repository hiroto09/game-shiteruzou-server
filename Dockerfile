FROM python:3.10-slim

WORKDIR /app

# 依存関係コピー & インストール
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# アプリコードコピー
COPY main.py /app/

# FastAPI ポート
EXPOSE 8000

# 起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
