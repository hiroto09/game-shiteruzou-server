from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from datetime import datetime
import mysql.connector  # ← MySQL接続用追加

# --- 環境変数読み込み ---
load_dotenv(verbose=True)

# --- Slackクライアント ---
slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))

# --- FastAPIアプリ作成 ---
app = FastAPI()

# --- 状態変数 ---
last_game_name = None
room_status = "何もしていない"
packet_status = False

# --- MySQL接続設定 ---
db_config = {
    "host": os.environ.get("DB_HOST", "db"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "game_results"),
    "port": int(os.environ.get("DB_PORT", "3306")),
}

def save_to_db(game_name: str, timestamp: str):
    """推論結果を MySQL に保存"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO results (game_name, timestamp)
            VALUES (%s, %s)
        """, (game_name, timestamp))
        conn.commit()
        print(f"✅ DB保存完了: {game_name} ({timestamp})")
    except Exception as e:
        print("⚠️ DB保存エラー:", e)
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


@app.post("/result")
async def receive_result(request: Request):
    global last_game_name, room_status, packet_status
    data = await request.json()
    print("受け取った推論結果:", data)

    game_name = data.get("class", "不明")

    # timestamp が指定されていなければ現在時刻を見やすい形式で補完
    raw_now = data.get("timestamp")
    if not raw_now or raw_now == "不明":
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    else:
        try:
            now = datetime.fromisoformat(raw_now).strftime("%Y/%m/%d %H:%M:%S")
        except Exception:
            now = str(raw_now)

    message = f"【{now}】\n {game_name}"

    # packet_status が False の場合、room_status が「何もしていない」以外なら更新しない
    if packet_status is False and room_status != "何もしていない":
        status = "skipped_by_packet"
    else:
        # 更新処理
        if game_name != last_game_name:
            # Slack通知
            slack_client.chat_postMessage(
                channel="#prj_game_shiteruzou",
                text=message
            )

            # MySQL保存
            save_to_db(game_name, now)

            last_game_name = game_name
            room_status = game_name
            status = "notified"
        else:
            status = "skipped"

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
    print("Slack Event Received:", data)

    if data.get("type") == "url_verification":
        return JSONResponse(content={"challenge": data["challenge"]})

    event = data.get("event", {})
    print("Event details:", event)

    return JSONResponse(content={"status": "ok"})


@app.post("/packet")
async def receive_packet(request: Request):
    global packet_status
    data = await request.json()
    print("Packet Received:", data)

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
