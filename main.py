from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from datetime import datetime
import mysql.connector
from io import BytesIO

load_dotenv(verbose=True)

CLASS_MAP = {
    0: "何もしてない",
    1: "人生ゲーム",
    2: "スマブラ"
}

slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
app = FastAPI()

last_room_status = "不明"
room_status = "不明"
packet_status = False
current_start_time = None

db_config = {
    "host": os.environ.get("DB_HOST", "db"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "game_results"),
    "port": int(os.environ.get("DB_PORT", "3306")),
}

# --- DB保存用関数 ---
def save_new_state(room_status_id: int, start_time: str, image_bytes: bytes = None):
    """新しい状態をDBに保存"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO results (room_status_id, start_time, image_blob)
            VALUES (%s, %s, %s)
        """, (room_status_id, start_time, image_bytes))
        conn.commit()
        print(f"✅ 新しい状態保存: {CLASS_MAP[room_status_id]} ({start_time}) 画像: {'あり' if image_bytes else 'なし'}")
    except Exception as e:
        print("⚠️ DB保存エラー:", e)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def close_last_state(end_time: str):
    """前の状態の終了時刻を更新"""
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
        print(f"🕒 前の状態終了を記録: {end_time}")
    except Exception as e:
        print("⚠️ 終了時刻更新エラー:", e)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

# --- /result エンドポイント ---
@app.post("/result")
async def receive_result(
    class_id: int = Form(...),
    confidence: float = Form(...),
    timestamp: str = Form(...),
    image: UploadFile = File(None)
):
    global last_room_status, room_status, packet_status, current_start_time

    # --- 時刻整形 ---
    try:
        now = datetime.fromisoformat(timestamp).strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    # --- 画像読み込み ---
    image_bytes = None
    if image:
        image_bytes = await image.read()
        print(f"🖼️ 画像受信: {image.filename} ({len(image_bytes)} bytes)")

    # --- 状態判定 ---
    if not packet_status:
        room_status_id = 0
        room_status = CLASS_MAP[room_status_id]
        print("⚠️ packet_status=False → 何もしてない")
    else:
        room_status_id = class_id
        room_status = CLASS_MAP.get(room_status_id, "不明")
        print("📥 推論結果:", {"class_id": class_id, "confidence": confidence})

    # --- 状態変化チェック ---
    if room_status == last_room_status:
        status = "skipped"
        print(f"⏩ 同じ状態スキップ: {room_status}")
    else:
        if last_room_status != "不明" and current_start_time:
            close_last_state(now)

        save_new_state(room_status_id, now, image_bytes)
        current_start_time = now

        # --- Slack送信 ---
        try:
            message = f"【{now}】\n{room_status}"
            if image_bytes:
                slack_client.files_upload(
                    channels="#prj_game_shiteruzo",
                    file=BytesIO(image_bytes),
                    filename=image.filename,
                    initial_comment=message
                )
                print(f"🔔 Slack送信（画像付き）: {message}")
            else:
                slack_client.chat_postMessage(
                    channel="#prj_game_shiteruzo",
                    text=message
                )
                print(f"🔔 Slack送信: {message}")
        except Exception as e:
            print(f"⚠️ Slack送信エラー: {e}")

        last_room_status = room_status
        status = "notified"

    return JSONResponse(content={
        "status": status,
        "room_status_id": room_status_id,
        "room_status_name": room_status,
        "packet_status": packet_status,
        "image_present": bool(image_bytes),
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
    return JSONResponse(content={"result": result, "packet_status": packet_status, "updated_at": now})

# --- /events エンドポイント ---
@app.post("/events")
async def slack_events(request: Request):
    data = await request.json()
    if data.get("type") == "url_verification":
        return JSONResponse(content={"challenge": data["challenge"]})
    return JSONResponse(content={"status": "ok"})
