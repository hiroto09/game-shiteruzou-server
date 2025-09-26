from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
from slack_sdk import WebClient

load_dotenv(verbose=True)

slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

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


@app.post("/events")
async def slack_events(request: Request):
    data = await request.json()
    print("Slack Event Received:", data)

    if data.get("type") == "url_verification":
        return JSONResponse(content={"challenge": data["challenge"]})

    event = data.get("event", {})
    print("Event details:", event)

    return JSONResponse(content={"status": "ok"})
