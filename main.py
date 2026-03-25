from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from datetime import datetime
import os
from dotenv import load_dotenv
import mysql.connector
from slack_sdk import WebClient

load_dotenv(verbose=True)

# =========================
# 定数
# =========================
CLASS_MAP = {
    0: "何もしてない",
    1: "人生ゲーム",
    2: "スマブラ",
    3: "マリオカート"
}

ANALOG_MAP = {
    "0": "何もしてない",
    "0437ac48be2a81": "カタカナーシ",
    "0433ac48be2a81": "チェス",
    "0434ac48be2a81": "モダンアート",
    "043aac48be2a81": "マーダーミステリー",
    "0435ac48be2a81": "UIかるた",
    "04f9ab48be2a81": "カラーコードかるた",
    "043dac48be2a81": "Linuxコマンドかるた",
    "043bac48be2a81": "トランプ",
    "0443ac48be2a81": "お邪魔者",
    "0411ac48be2a81": "カタン(大航海時代)",
    "0444ac48be2a81": "キャンプ場の殺人鬼",
    "0449ac48be2a81": "コヨーテ",
    "0412ac48be2a81": "犯人は踊る",
    "043fac48be2a81": "犯人は踊る3",
    "043cac48be2a81": "お邪魔者2",
    "043eac48be2a81": "トランプ",
    "0441ac48be2a81": "ファットプロジェクト",
    "04ffab48be2a81": "プログラム言語神経衰弱",
    "04faab48be2a81": "テストプレイなんてしてないよ",
    "0445ac48be2a81": "まじかる★ベーカリー",
    "0442ac48be2a81": "カタン(スタンダート)",
    "0436ac48be2a81": "カタン(スタンダート)",
    "0421ac48be2a81": "ito",
    "0413ac48be2a81": "人狼",
    "0418ac48be2a81": "プロポーズ",
    "0432ac48be2a81": "麻雀"
}

CHANNEL = "#prj_game_shiteruzo"

slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
app = FastAPI()

# =========================
# 状態管理
# =========================
class State:
    def __init__(self):
        self.digital = "何もしてない"
        self.last_digital = "不明"
        self.digital_start_time = None

        self.analog = "何もしてない"
        self.last_analog = "不明"
        self.analog_start_time = None

        self.packet = False

state = State()

# =========================
# 🔥 WebSocket追加
# =========================
clients = []

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)

    # 接続時に現在のanalog送る
    await ws.send_json({
        "analog": state.analog
    })

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.remove(ws)

async def notify():
    for ws in clients:
        try:
            await ws.send_json({
                "analog": state.analog
            })
        except:
            pass

# =========================
# DB設定
# =========================
db_config = {
    "host": os.environ.get("DB_HOST", "db"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "game_results"),
    "port": int(os.environ.get("DB_PORT", "3306")),
}

def execute_db(query, params=None):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        conn.commit()
    except Exception as e:
        print("⚠️ DBエラー:", e)
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

# =========================
# digital DB
# =========================
def save_digital_start(status_id, start_time):
    execute_db(
        "INSERT INTO digital_results (status_id, start_time) VALUES (%s, %s)",
        (status_id, start_time)
    )

def close_digital(end_time):
    execute_db(
        """UPDATE digital_results SET end_time=%s
           WHERE end_time IS NULL
           ORDER BY id DESC LIMIT 1""",
        (end_time,)
    )

# =========================
# analog DB
# =========================
def save_analog_start(tag_id, start_time):
    execute_db(
        "INSERT INTO analog_results (tag_id, start_time) VALUES (%s, %s)",
        (tag_id, start_time)
    )

def close_analog(end_time):
    execute_db(
        """UPDATE analog_results SET end_time=%s
           WHERE end_time IS NULL
           ORDER BY id DESC LIMIT 1""",
        (end_time,)
    )

# =========================
# 共通
# =========================
def now_str():
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

def parse_time(ts):
    try:
        return datetime.fromisoformat(ts).strftime("%Y/%m/%d %H:%M:%S")
    except:
        return now_str()

def create_blocks():
    return [
        {"type": "header", "text": {"type": "plain_text", "text": "状態リスト"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"🎮 :{state.digital}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"🃏 :{state.analog}"}}
    ]

def send_slack(text):
    try:
        slack_client.chat_postMessage(
            channel=CHANNEL,
            text=text,
            blocks=create_blocks()
        )
    except Exception as e:
        print("⚠️ Slackエラー:", e)

# =========================
# /result（digital）
# =========================
@app.post("/result")
async def result(request: Request):
    data = await request.json()

    try:
        class_id = int(data["class_id"])
        now = parse_time(data["timestamp"])
    except:
        raise HTTPException(422, "Invalid JSON")

    digital_id = 0 if not state.packet else class_id
    new_digital = CLASS_MAP.get(digital_id, "不明")

    if new_digital != state.last_digital:

        if state.last_digital != "不明" and state.digital_start_time:
            close_digital(now)

        if new_digital != "何もしてない":
            save_digital_start(digital_id, now)
            state.digital_start_time = now
        else:
            state.digital_start_time = None

        state.last_digital = new_digital
        state.digital = new_digital

        send_slack(new_digital)

    return JSONResponse({
        "digital_status_name": state.digital
    })

# =========================
# /analog（ここだけ通知追加🔥）
# =========================
@app.post("/analog")
async def analog(request: Request):
    data = await request.json()

    try:
        tag = data["tag_id"]
    except:
        raise HTTPException(422, "Invalid JSON")

    now = now_str()
    new_analog = ANALOG_MAP.get(tag, "何もしてない")

    if new_analog != state.last_analog:

        if state.last_analog != "不明" and state.analog_start_time:
            close_analog(now)

        if new_analog != "何もしてない":
            save_analog_start(tag, now)
            state.analog_start_time = now
        else:
            state.analog_start_time = None

        state.last_analog = new_analog
        state.analog = new_analog

        send_slack(new_analog)
        await notify()  # ← 🔥 これだけ追加

    return JSONResponse({
        "analog_status": state.analog
    })

# =========================
# /packet
# =========================
@app.post("/packet")
async def packet(request: Request):
    data = await request.json()

    if isinstance(data.get("status"), bool):
        state.packet = data["status"]

    return {"packet": state.packet}

# =========================
# /events
# =========================
@app.post("/events")
async def events(request: Request):
    data = await request.json()

    if data.get("type") == "url_verification":
        return {"challenge": data["challenge"]}

    return {"status": "ok"}