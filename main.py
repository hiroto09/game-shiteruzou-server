from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
import asyncio
from slack_sdk import WebClient
import requests  # ← 追加

load_dotenv()

# =========================
# 定数
# =========================
DIGITAL_MAP = {
    "0": "何もしてない",
    "1": "人生ゲーム",
    "2": "スマブラ",
    "3": "マリオカート"
}

ANALOG_MAP = {
    "00": "何もしてない",
    "01": "カタカナーシ", 
    "02": "チェス", 
    "03": "モダンアート", 
    "04": "マーダーミステリー", 
    "05": "UIかるた",
    "06": "カラーコードかるた", 
    "07": "Linuxコマンドかるた", 
    "08": "トランプ", 
    "09": "お邪魔者", 
    "10": "カタン(大航海時代)", 
    "11": "キャンプ場の殺人鬼", 
    "12": "コヨーテ", 
    "13": "犯人は踊る", 
    "14": "犯人は踊る3", 
    "15": "お邪魔者2", 
    "16": "トランプ", 
    "17": "ファットプロジェクト", 
    "18": "プログラム言語神経衰弱", 
    "19": "テストプレイなんてしてないよ", 
    "20": "まじかる★ベーカリー", 
    "21": "カタン(スタンダート)", 
    "22": "カタン(スタンダート)", 
    "23": "ito", 
    "24": "人狼", 
    "25": "プロポーズ", 
    "26": "麻雀",
    "27": "宝石の煌めき"
}


EMPTY_ID = 0
CHANNEL = "#prj_game_shiteruzo"
LOG_API_URL = os.getenv("LOG_API_URL")
slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
STAYWATCH_API_URL = os.getenv("STAYWATCH_API_URL")
STAYWATCH_API_KEY = os.getenv("STAYWATCH_API_KEY")

app = FastAPI()

JST = timezone(timedelta(hours=9))

# =========================
# 状態管理
# =========================
class State:
    def __init__(self):
        # digital
        self.digital = "何もしてない"
        self.last_digital = None
        self.last_digital_id = None
        self.digital_start_time = None

        # analog
        self.analog = "何もしてない"
        self.last_analog = None
        self.last_analog_id = None
        self.analog_start_time = None

        self.packet = False

state = State()

# =========================
# utils
# =========================



def send_log(event_id, event_time, status):
    try:
        res = requests.post(
            LOG_API_URL,
            json={
                "logs": [
                    {
                        "event_id": event_id,
                        "event_time": event_time,  # ← こっち使う
                        "status_id": status
                    }
                ]
            },
        )

        print("LOG SEND:",
            "event_id=", event_id,
            "status=", status,
            "HTTP=", res.status_code,
            "response=", res.text)

    except Exception as e:
        print("ログ送信エラー:", e)

def send_slack():
    try:
        print("📢 Slack送信開始")
        print("channel:", CHANNEL)
        print("digital:", state.digital)
        print("analog:", state.analog)

        response = slack_client.chat_postMessage(
            channel=CHANNEL,
            text="状態更新",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🎮 {state.digital}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🃏 {state.analog}"
                    }
                }
            ]
        )

        print("✅ Slack送信成功")
        print("Slack response:", response)

    except Exception as e:
        print("❌ Slackエラー:")
        print(type(e).__name__)
        print(e)


## =========================
## メンバー一覧取得
## =========================

def get_stayers():
    if not STAYWATCH_API_URL or not STAYWATCH_API_KEY:
        raise HTTPException(500, "環境変数が設定されていません")

    try:
        res = requests.get(
            STAYWATCH_API_URL,
            headers={
                "X-API-Key": STAYWATCH_API_KEY
            },
            timeout=5
        )

        if res.status_code != 200:
            raise HTTPException(res.status_code, "外部APIエラー")

        return res.json()

    except requests.RequestException as e:
        print("🔥 requestsエラー:", e)
        raise HTTPException(500, f"外部API接続エラー: {e}")
    

# =========================
# WebSocket
# =========================
clients = []
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)

    await ws.send_json({
        "analog": state.analog,
        "users": []
    })

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.remove(ws)


async def notify():
    users = []

    if state.analog != "何もしてない":
        try:
            loop = asyncio.get_event_loop()
            stayers = await loop.run_in_executor(None, get_stayers)

            users = [user["name"] for user in stayers]
        except Exception as e:
            print("stayers取得エラー:", e)
            users = []

    for ws in clients:
        try:
            await ws.send_json({
                "analog": state.analog,
                "users": users
            })
        except:
            pass

# =========================
# digital
# =========================
@app.post("/digital")
async def result(request: Request):
    data = await request.json()

    try:
        class_id = int(data["class_id"])
        now = datetime.now(JST).isoformat()
    except:
        raise HTTPException(422, "Invalid JSON")

    digital_id = str(class_id)
    new_digital = DIGITAL_MAP.get(digital_id, "不明")

    if digital_id != state.last_digital_id:

        # 終了
        if state.last_digital_id is not None:
            send_log(state.last_digital_id, now, 2)

        # 開始
        send_log(digital_id, now, 1)

        state.last_digital_id = digital_id
        state.digital = new_digital

        send_slack()

    return {"digital_status_name": state.digital}

# =========================
# analog
# =========================
@app.post("/analog")
async def analog(request: Request):
    data = await request.json()

    id = data.get("analog_id")
    if id is None:
        raise HTTPException(422, "Invalid JSON")

    now = datetime.now(JST).isoformat()

    analog_id = id if id in ANALOG_MAP else "0"
    new_analog = ANALOG_MAP.get(analog_id, "何もしてない")

    if analog_id != state.last_analog_id:

        # 終了
        if state.last_analog_id is not None:
            send_log(state.last_analog_id, now, 2)

        # 開始
        send_log(analog_id, now, 1)

        state.last_analog_id = analog_id
        state.analog = new_analog

        send_slack()
        await notify()

    return {"analog_status": state.analog}

# =========================
# packet
# =========================
# @app.post("/packet")
# async def packet(request: Request):
#     data = await request.json()
#     if isinstance(data.get("status"), bool):
#         state.packet = data["status"]
#     return {"packet": state.packet}

# =========================
# events
# =========================
@app.post("/events")
async def events(request: Request):
    data = await request.json()
    if data.get("type") == "url_verification":
        return {"challenge": data["challenge"]}
    return {"status": "ok"}