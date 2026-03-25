from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from datetime import datetime
import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

app = FastAPI()

# =========================
# 状態
# =========================
class State:
    analog = "何もしてない"
    last_analog = "不明"

# =========================
# マップ
# =========================
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

# =========================
# DB
# =========================
db_config = {
    "host": os.getenv("DB_HOST", "db"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "game_results"),
    "port": int(os.getenv("DB_PORT", "3306")),
}

def execute_db(query, params=None, fetch=False):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        conn.commit()

        if fetch:
            return cursor.fetchall()

    except Exception as e:
        print("DBエラー:", e)
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

# =========================
# analog DB操作
# =========================
def save_analog(tag, start):
    execute_db(
        "INSERT INTO analog_results (tag_id, start_time) VALUES (%s, %s)",
        (tag, start)
    )

def close_analog(end):
    execute_db(
        """UPDATE analog_results
           SET end_time=%s
           WHERE end_time IS NULL
           ORDER BY id DESC LIMIT 1""",
        (end,)
    )

# =========================
# WebSocket
# =========================
clients = []

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.remove(ws)

async def notify():
    for ws in clients:
        try:
            await ws.send_json({"analog": State.analog})
        except:
            pass

# =========================
# util
# =========================
def now():
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

# =========================
# 起動時復元（重要🔥）
# =========================
@app.on_event("startup")
def load_state():
    result = execute_db(
        """SELECT * FROM analog_results
           WHERE end_time IS NULL
           ORDER BY id DESC LIMIT 1""",
        fetch=True
    )

    if result:
        tag = result[0]["tag_id"]
        State.analog = ANALOG_MAP.get(tag, "何もしてない")

# =========================
# analog API
# =========================
@app.post("/analog")
async def analog(request: Request):
    data = await request.json()

    try:
        tag = data["tag_id"]
    except:
        raise HTTPException(422, "Invalid JSON")

    current = ANALOG_MAP.get(tag, "何もしてない")
    t = now()

    # 状態変化のみ処理
    if current != State.analog:

        # 前を閉じる
        if State.analog != "何もしてない":
            close_analog(t)

        # 新規保存（何もしてない以外）
        if tag != "0":
            save_analog(tag, t)

        State.last_analog = State.analog
        State.analog = current

        # Web通知
        await notify()

        status = "saved"
    else:
        status = "skipped"

    return JSONResponse({
        "status": status,
        "analog": State.analog,
        "time": t
    })

# =========================
# HTML配信
# =========================
@app.get("/", response_class=HTMLResponse)
async def index():
    return open("index.html").read()