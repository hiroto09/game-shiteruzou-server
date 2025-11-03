from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from datetime import datetime
import mysql.connector

# --- 環境変数読み込み ---
load_dotenv(verbose=True)

# --- クラスIDと日本語名の対応 ---
CLASS_MAP = {
    0: "何もしてない",
    1: "人生ゲーム",
    2: "スマブラ"
}

# --- Slackクライアント ---
slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

# --- FastAPIアプリ作成 ---
app = FastAPI()

# --- 状態変数 ---
last_room_status = "不明"
room_status = "不明"
packet_status = False

# --- MySQL接続設定 ---
db_config = {
    "host": os.environ.get("DB_HOST", "db"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "game_results"),
    "port": int(os.environ.get("DB_PORT", "3306")),
}

# --- DB保存関数 ---
def save_to_db(room_status_id: int, timestamp: str):
    """推論結果を MySQL に保存（IDで）"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO results (room_status_id, timestamp)
            VALUES (%s, %s)
        """, (room_status_id, timestamp))
        conn.commit()
        print(f"✅ DB保存完了: ID={room_status_id} ({timestamp})")
    except Exception as e:
        print("⚠️ DB保存エラー:", e)
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()


# --- /result エンドポイント ---
@app.post("/result")
async def receive_result(request: Request):
    global last_room_status, room_status, packet_status
    data = await request.json()

    raw_now = data.get("timestamp")
    if not raw_now or raw_now == "不明":
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    else:
        try:
            now = datetime.fromisoformat(raw_now).strftime("%Y/%m/%d %H:%M:%S")
        except Exception:
            now = str(raw_now)

    # --- packet_statusがFalseなら強制的に「何もしてない」 ---
    if not packet_status:
        room_status_id = 0
        room_status = CLASS_MAP[room_status_id]
        print(f"⚠️ packet_status=False → 「何もしてない」に設定")
    else:
        room_status_id = int(data.get("class_id", 0))
        room_status = CLASS_MAP.get(room_status_id, "不明")
        print("📥 推論結果受信:", data)

    # --- 同一状態はスキップ ---
    if room_status == last_room_status:
        status = "skipped"
        print(f"⏩ 同じ状態スキップ: {room_status}")
    else:
        # --- Slack通知 ---
        try:
            message = f"【{now}】\n{room_status}"
            slack_client.chat_postMessage(
                channel="#prj_game_shiteruzo",
                text=message
            )
            print(f"🔔 Slack送信: {message}")
        except Exception as e:
            print(f"⚠️ Slack送信エラー: {e}")

        # --- DB保存 ---
        save_to_db(room_status_id, now)

        last_room_status = room_status
        status = "notified"

    return JSONResponse(content={
        "status": status,
        "received": data,
        "room_status_id": room_status_id,
        "room_status_name": room_status,
        "packet_status": packet_status,
        "formatted_time": now
    })


# --- /packet エンドポイント ---
@app.post("/packet")
async def receive_packet(request: Request):
    global packet_status
    data = await request.json()
    print("📥 Packet Received:", data)

    new_status = data.get("status")
    if isinstance(new_status, bool):
        packet_status = new_status
        result = "updated"
    else:
        result = "invalid"

    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    return JSONResponse(content={
        "result": result,
        "packet_status": packet_status,
        "updated_at": now
    })


# --- /events (Slack Event受信用) ---
@app.post("/events")
async def slack_events(request: Request):
    data = await request.json()
    print("📥 Slack Event Received:", data)

    if data.get("type") == "url_verification":
        return JSONResponse(content={"challenge": data["challenge"]})

    event = data.get("event", {})
    print("Event details:", event)

    return JSONResponse(content={"status": "ok"})
