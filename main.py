from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from datetime import datetime
import mysql.connector

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

# --- 状態の開始時刻を記録 ---
current_start_time = None

db_config = {
    "host": os.environ.get("DB_HOST", "db"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "game_results"),
    "port": int(os.environ.get("DB_PORT", "3306")),
}


def save_new_state(room_status_id: int, start_time: str):
    """新しい状態の開始をDBに保存"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO results (room_status_id, start_time)
            VALUES (%s, %s)
        """, (room_status_id, start_time))
        conn.commit()
        print(f"✅ 新しい状態保存: {CLASS_MAP[room_status_id]} ({start_time})")
    except Exception as e:
        print("⚠️ DB保存エラー:", e)
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
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
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()


@app.post("/result")
async def receive_result(request: Request):
    global last_room_status, room_status, packet_status, current_start_time
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
        # --- 前の状態を終了 ---
        if last_room_status != "不明" and current_start_time:
            close_last_state(now)

        # --- 新しい状態の開始 ---
        save_new_state(room_status_id, now)
        current_start_time = now

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

@app.post("/packet")
async def receive_packet(request: Request):
    """
    通信状態（packet_status）の更新API。
    例: {"status": true} または {"status": false}
    """
    global packet_status
    data = await request.json()

    new_status = data.get("status")
    if new_status is None:
        return JSONResponse(content={"error": "statusが指定されていません"}, status_code=400)

    packet_status = bool(new_status)
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    print(f"📡 パケット状態更新: {packet_status} at {now}")


    return JSONResponse(content={
        "status": "ok",
        "packet_status": packet_status,
        "timestamp": now
    })


@app.post("/event")
async def receive_event(request: Request):
    """
    任意イベントをSlackに送信。
    例: {"message": "システム再起動しました"}
    """
    data = await request.json()
    message = data.get("message", "（メッセージなし）")
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    try:
        slack_client.chat_postMessage(
            channel="#prj_game_shiteruzo",
            text=f"【イベント】{now}\n{message}"
        )
        print(f"📝 イベント送信: {message}")
    except Exception as e:
        print(f"⚠️ Slack送信エラー: {e}")

    return JSONResponse(content={"status": "sent", "message": message, "timestamp": now})
