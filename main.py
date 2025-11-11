from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import os
from dotenv import load_dotenv
import mysql.connector
from slack_sdk import WebClient

load_dotenv(verbose=True)

CLASS_MAP = {
    0: "何もしてない",
    1: "人生ゲーム",
    2: "スマブラ"
}

slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
app = FastAPI()

# 画像保存用ディレクトリ
IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

# 静的配信設定
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")

# 状態管理
last_room_status = "不明"
room_status = "不明"
packet_status = False
current_start_time = None

# DB接続情報
db_config = {
    "host": os.environ.get("DB_HOST", "db"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "game_results"),
    "port": int(os.environ.get("DB_PORT", "3306")),
}

# =========================================
# DB保存関数
def save_new_state(room_status_id: int, start_time: str):
    """新しい状態をresultsに保存"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO results (room_status_id, start_time)
            VALUES (%s, %s)
        """, (room_status_id, start_time))
        conn.commit()
        print(f"✅ 新しい状態保存: {CLASS_MAP[room_status_id]} ({start_time})")
        return cursor.lastrowid
    except Exception as e:
        print("⚠️ DB保存エラー:", e)
        return None
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def close_last_state(end_time: str):
    """最後の状態にend_timeを記録"""
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

def save_image_record(image_url: str, saved_time: str):
    """imagesテーブルに画像URLと保存時刻を登録"""
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO images (result_id, image_url, saved_time)
            VALUES (%s, %s, %s)
        """, (image_url, saved_time))
        conn.commit()
        print(f"🖼️ 画像保存記録: {image_url} ({saved_time})")
    except Exception as e:
        print("⚠️ 画像記録エラー:", e)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

# =========================================
# /result エンドポイント
@app.post("/result")
async def receive_result(
    class_id: int = Form(...),
    confidence: float = Form(...),
    timestamp: str = Form(...),
    image: UploadFile = File(None)
):
    global last_room_status, room_status, packet_status, current_start_time

    # 時刻整形
    try:
        now = datetime.fromisoformat(timestamp).strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    # 状態判定
    if not packet_status:
        room_status_id = 0
        room_status = CLASS_MAP[room_status_id]
        print("⚠️ packet_status=False → 何もしてない")
    else:
        room_status_id = class_id
        room_status = CLASS_MAP.get(room_status_id, "不明")
        print("📥 推論結果:", {"class_id": class_id, "confidence": confidence})

    result_id = None

    # 状態変化チェック & DB保存
    if room_status != last_room_status:
        if last_room_status != "不明" and current_start_time:
            close_last_state(now)
        result_id = save_new_state(room_status_id, now)
        current_start_time = now
        last_room_status = room_status

        # Slack通知
        try:
            message = f"【{now}】\n{room_status}"
            slack_client.chat_postMessage(channel="#prj_game_shiteruzo", text=message)
            print(f"🔔 Slack送信: {message}")
        except Exception as e:
            print(f"⚠️ Slack送信エラー: {e}")

        status = "saved"
    else:
        # 状態変化なしでも最後のresult_idを取得
        try:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM results ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                result_id = row[0]
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
        status = "skipped"

    # 画像保存処理（状態変化に関係なく毎回）
    if image:
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image.filename}"
        save_path = os.path.join(IMAGE_DIR, filename)
        with open(save_path, "wb") as f:
            f.write(await image.read())

        image_url = f"/images/{filename}"
        save_image_record(image_url, now)

    return JSONResponse({
        "status": status,
        "room_status_name": room_status,
        "packet_status": packet_status,
        "image_saved": bool(image),
        "formatted_time": now
    })

# =========================================
# /packet エンドポイント
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
    return JSONResponse({"result": result, "packet_status": packet_status, "updated_at": now})

# =========================================
# /events エンドポイント
@app.post("/events")
async def slack_events(request: Request):
    data = await request.json()
    if data.get("type") == "url_verification":
        return JSONResponse({"challenge": data["challenge"]})
    return JSONResponse({"status": "ok"})
