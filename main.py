import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# .env を読み込む
load_dotenv(verbose=True)

# Slackクライアントを初期化
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#prj_game_shiteruzou")

if not SLACK_BOT_TOKEN:
    raise ValueError("SLACK_BOT_TOKEN が .env に設定されていません。")

slack_client = WebClient(token=SLACK_BOT_TOKEN)

# FastAPI アプリ
app = FastAPI()

# 直前のゲーム名を保持
last_game_name = None

@app.post("/result")
async def receive_result(request: Request):
    """
    推論結果を受け取り Slack に通知するエンドポイント
    """
    global last_game_name
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(content={"status": "error", "message": "Invalid JSON"}, status_code=400)

    print("受け取った推論結果:", data)

    game_name = data.get("class", "不明")
    timestamp = data.get("timestamp", "不明")
    message = f"【{timestamp}】 {game_name}"

    # 直前のゲーム名と同じ場合は通知しない
    if game_name != last_game_name:
        try:
            slack_client.chat_postMessage(channel=SLACK_CHANNEL, text=message)
            last_game_name = game_name
            status = "notified"
        except Exception as e:
            print("Slack通知エラー:", e)
            status = "error"
    else:
        status = "skipped"

    return JSONResponse(content={"status": status, "received": data})
