from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import os
from dotenv import load_dotenv
import mysql.connector
from slack_sdk import WebClient

# =========================
# 初期設定
# =========================
load_dotenv(verbose=True)

app = FastAPI()

CLASS_MAP = {
    0: "何もしてない",
    1: "人生ゲーム",
    2: "スマブラ",
    3: "マリオカート"
}

CONF_THRESHOLD = 0.6
IGNORE_CLASS_ID = 0

slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

# =========================
# 状態管理
# =========================
last_room_status = "不明"
current_start_time = None
packet_status = False

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

# =========================
# DB操作
# =========================
def save_new_state(room_status_id: int, start_time: str):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO results (room_status_id, start_time) VALUES (%s, %s)",
            (room_status_id, start_time)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def close_last_state(end_time: str):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE results
            SET end_time = %s
            WHERE end_time IS NULL
            ORDER BY id DESC
            LIMIT 1
        """, (end_time,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# =========================
# /result（推定結果受信）
# =========================
@app.post("/result")
async def receive_result(request: Request):
    global last_room_status, current_start_time, packet_status

    data = await request.json()

    class_id = int(data.get("class_id"))
    confidence = float(data.get("confidence"))
    timestamp = data.get("timestamp")

    # ---- confidence フィルタ ----
    if confidence < CONF_THRESHOLD:
        return JSONResponse({"status": "ignored", "reason": "low_confidence"})

    # ---- packet_status ----
    if not packet_status:
        return JSONResponse({"status": "ignored", "reason": "packet_off"})

    # ---- 無視クラス ----
    if class_id == IGNORE_CLASS_ID:
        return JSONResponse({"status": "ignored", "reason": "idle_state"})

    # ---- 時刻整形 ----
    try:
        now = datetime.fromisoformat(timestamp).strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    room_status = CLASS_MAP.get(class_id, "不明")

    # ---- 状態変化なし → 何もしない ----
    if room_status == last_room_status:
        return JSONResponse({"status": "skipped", "room_status": room_status})

    # ---- 状態変化あり ----
    if last_room_status != "不明" and current_start_time:
        close_last_state(now)

    save_new_state(class_id, now)
    current_start_time = now
    last_room_status = room_status

    # ---- Slack通知 ----
    try:
        slack_client.chat_postMessage(
            channel="#prj_game_shiteruzo",
            text=f"\n🎮 {room_status}をプレイ中！一緒に遊ぼう！"
        )
    except Exception as e:
        print("⚠️ Slack送信エラー:", e)

    return JSONResponse({
        "status": "saved",
        "room_status": room_status,
        "confidence": confidence,
        "time": now
    })

# =========================
# /packet（在室判定）
# =========================
@app.post("/packet")
async def receive_packet(request: Request):
    global packet_status

    data = await request.json()
    new_status = data.get("status")

    if isinstance(new_status, bool):
        packet_status = new_status
        result = "updated"
    else:
        result = "invalid"

    return JSONResponse({
        "result": result,
        "packet_status": packet_status,
        "updated_at": datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    })

# =========================
# Slack Events（URL検証）
# =========================
@app.post("/events")
async def slack_events(request: Request):
    data = await request.json()
    if data.get("type") == "url_verification":
        return JSONResponse({"challenge": data["challenge"]})
    return JSONResponse({"status": "ok"})
