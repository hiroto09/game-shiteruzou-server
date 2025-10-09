from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from datetime import datetime
import mysql.connector  # MySQL接続用

# --- 環境変数読み込み ---
load_dotenv(verbose=True)

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

def save_to_db(room_status: str, timestamp: str):
    """推論結果を MySQL に保存"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO results (room_status, timestamp)
            VALUES (%s, %s)
        """, (room_status, timestamp))
        conn.commit()
        print(f"✅ DB保存完了: {room_status} ({timestamp})")
    except Exception as e:
        print("⚠️ DB保存エラー:", e)
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()


@app.post("/result")
async def receive_result(request: Request):
    global last_room_status, room_status, packet_status
    data = await request.json()

    # timestamp 処理
    raw_now = data.get("timestamp")
    if not raw_now or raw_now == "不明":
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    else:
        try:
            now = datetime.fromisoformat(raw_now).strftime("%Y/%m/%d %H:%M:%S")
        except Exception:
            now = str(raw_now)

    # --- packet_status に応じた処理 ---
    if packet_status is False:
        room_status = "何もしていない"
        print(f"⚠️ packet_status=False → 推論結果を無視して room_status を「何もしていない」に設定")
    else:
        # packet_status=True の場合のみ受信データを反映
        room_status = data.get("class", "不明")
        print("📥 受け取った推論結果:", data)

    # --- 同じ状態ならスキップ ---
    if room_status == last_room_status:
        status = "skipped"
        print(f"⏩ 同じ状態のため処理スキップ → last_room_status: {last_room_status}, room_status: {room_status}, timestamp: {now}")
    else:
        # Slack送信前ログ
        print(f"🔔 Slack送信前 → packet_status: {packet_status}, room_status: {room_status}, timestamp: {now}")

        # Slack通知
        try:
            message = f"【{now}】\n {room_status}"
            slack_client.chat_postMessage(
                channel="#prj_game_shiteruzou",
                text=message
            )
        except Exception as e:
            print(f"⚠️ Slack送信エラー: {e}")

        # DB保存
        save_to_db(room_status, now)

        last_room_status = room_status
        status = "notified"

    return JSONResponse(content={
        "status": status,
        "received": data,
        "room_status": room_status,
        "packet_status": packet_status,
        "formatted_time": now
    })


@app.post("/events")
async def slack_events(request: Request):
    data = await request.json()
    print("📥 Slack Event Received:", data)

    if data.get("type") == "url_verification":
        return JSONResponse(content={"challenge": data["challenge"]})

    event = data.get("event", {})
    print("Event details:", event)

    return JSONResponse(content={"status": "ok"})


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
