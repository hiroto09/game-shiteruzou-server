import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv(verbose=True)

# Slackクライアントを初期化
slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

# FastAPI アプリ
app = FastAPI()


last_game_name = None

@app.post("/result")
async def receive_result(request: Request):
    global last_game_name
    data = await request.json()
    print("受け取った推論結果:", data)

    game_name = data.get("class", "不明")
    now = data.get("timestamp", "不明")
    message = f"【{now}】\n {game_name}"

    # 直前のゲーム名と同じ場合は通知しない
    if game_name != last_game_name:
        slack_client.chat_postMessage(
            channel="#prj_game_shiteruzou",
            text=message
        )
        last_game_name = game_name
        status = "notified"
    else:
        status = "skipped"

    return JSONResponse(content={"status": status, "received": data})
