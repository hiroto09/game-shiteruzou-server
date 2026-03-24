from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
import os
from dotenv import load_dotenv
import mysql.connector
from slack_sdk import WebClient

load_dotenv(verbose=True)

CLASS_MAP = {
    0: "何もしてない",
    1: "人生ゲーム",
    2: "スマブラ",
    3: "マリオカート"
}

ANALOG_MAP = {
    "0": "何もしてない",
    "0437ac48be2a81": "カタン",
}

slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
app = FastAPI()

# 状態管理
last_room_status = "不明"
room_status = "何もしてない"
last_analog_status = "不明"
analog_status = "何もしてない"
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
# 🔥 Block作成（何もしてないも必ず表示）
def create_game_blocks(digital, analog):
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "状態リスト"
            }
        }
    ]

    # デジタル
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"🎮 :{digital}"
        }
    })

    # アナログ
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"🎲 :{analog}"
        }
    })

    return blocks

# =========================================
# slack送信関数
def post_or_update_slack():
    global slack_ts

    blocks = create_game_blocks(room_status, analog_status)

    try:
        if slack_ts is None:
            # 初回投稿
            res = slack_client.chat_postMessage(
                channel=CHANNEL_ID,
                text="状態リスト",
                blocks=blocks
            )
            slack_ts = res["ts"]
        else:
            # 更新
            slack_client.chat_update(
                channel=CHANNEL_ID,
                ts=slack_ts,
                text="状態リスト",
                blocks=blocks
            )

    except Exception as e:
        print("⚠️ Slack更新エラー:", e)

# =========================================
# DB保存関数
def save_new_state(room_status_id: int, start_time: str):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO results (room_status_id, start_time)
            VALUES (%s, %s)
        """, (room_status_id, start_time))
        conn.commit()
    except Exception as e:
        print("⚠️ DB保存エラー:", e)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
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
    except Exception as e:
        print("⚠️ 終了時刻更新エラー:", e)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


# =========================================
# /result エンドポイント
@app.post("/result")
async def receive_result(request: Request):
    global last_room_status, room_status, packet_status, current_start_time

    data = await request.json()

    try:
        class_id = int(data["class_id"])
        timestamp = data["timestamp"]
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON format")

    # 時刻整形
    try:
        now = datetime.fromisoformat(timestamp).strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    # 状態判定
    if not packet_status:
        room_status_id = 0
        room_status = CLASS_MAP[room_status_id]
    else:
        room_status_id = class_id
        room_status = CLASS_MAP.get(room_status_id, "不明")


    # 状態変化チェック
    if room_status != last_room_status:

        if last_room_status != "不明" and current_start_time:
            close_last_state(now)

        save_new_state(room_status_id, now)
        current_start_time = now
        last_room_status = room_status

        # ===============================
        # 🔥 Slack送信（リスト表示）
        # ===============================
        try:
            blocks = create_game_blocks(room_status, analog_status)

            slack_client.chat_postMessage(
                channel="#prj_game_shiteruzo",
                text=room_status,  # fallback
                blocks=blocks
            )


        except Exception as e:
            print(f"⚠️ Slack送信エラー: {e}")

        status = "saved"
    else:
        status = "skipped"

    return JSONResponse({
        "status": status,
        "room_status_name": room_status,
        "packet_status": packet_status,
        "formatted_time": now
    })

# =========================================
# /analog エンドポイント
@app.post("/analog")
async def receive_analog(request: Request):
    global analog_status, last_analog_status, room_status

    data = await request.json()

    try:
        tag_id = data["tag_id"]  # NFCから送る
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON")

    # 🔥 タグ → ゲーム名
    analog_status = ANALOG_MAP.get(tag_id, "何もしてない")

    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")


    try:
        blocks = create_game_blocks(
            digital=room_status,
            analog=analog_status
        )

        slack_client.chat_postMessage(
            channel="#prj_game_shiteruzo",
            text= analog_status,
            blocks=blocks
        )

    except Exception as e:
        print(f"⚠️ Slack送信エラー: {e}")

    last_analog_status = analog_status
    status = "updated"

    return JSONResponse({
        "status": status,
        "analog_status": analog_status,
        "time": now
    })

# =========================================
# /packet エンドポイント
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

    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    return JSONResponse({
        "result": result,
        "packet_status": packet_status,
        "updated_at": now
    })


# =========================================
# /events エンドポイント
@app.post("/events")
async def slack_events(request: Request):
    data = await request.json()

    if data.get("type") == "url_verification":
        return JSONResponse({"challenge": data["challenge"]})

    return JSONResponse({"status": "ok"})