from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
import asyncio
from slack_sdk import WebClient
import requests


load_dotenv()


# =========================
# 定数
# =========================

EMPTY_ID = 0

CHANNEL = "#prj_game_shiteruzo"

LOG_API_URL = os.getenv("LOG_API_URL")

STAYWATCH_API_URL = os.getenv("STAYWATCH_API_URL")
STAYWATCH_API_KEY = os.getenv("STAYWATCH_API_KEY")
EVENTS_API_URL = os.getenv("EVENTS_API_URL")

slack_client = WebClient(
    token=os.environ.get("SLACK_BOT_TOKEN")
)


# =========================
# ゲームマップ
# =========================
#
# StayWatch APIから取得した
# ID -> ゲーム名
#
# 0だけはAPIに存在しない
# 「何もしてない」用として残す
#

GAME_MAP = {
    "0": "何もしてない"
}


# =========================
# FastAPI
# =========================

app = FastAPI()

JST = timezone(
    timedelta(hours=9)
)


# =========================
# 状態管理
# =========================

class State:

    def __init__(self):

        # ---------------------
        # digital
        # ---------------------

        self.digital = "何もしてない"
        self.last_digital = None
        self.last_digital_id = None
        self.digital_start_time = None

        # ---------------------
        # analog
        # ---------------------

        self.analog = "何もしてない"
        self.last_analog = None
        self.last_analog_id = None
        self.analog_start_time = None

state = State()


# =========================
# ゲーム一覧取得
# =========================

def update_game_map():

    global GAME_MAP

    try:

        print(
            "🎮 ゲーム一覧をAPIから取得します"
        )

        response = requests.get(
            EVENTS_API_URL,
            timeout=10
        )

        print(
            "EVENTS API:",
            response.status_code
        )

        response.raise_for_status()


        # ---------------------
        # JSON取得
        # ---------------------

        games = response.json()["data"]


        # ---------------------
        # 何もしてないだけ残す
        # ---------------------

        new_game_map = {
            "0": "何もしてない"
        }


        # ---------------------
        # ゲーム一覧を登録
        # ---------------------

        for game in games:

            game_id = str(
                game["ID"]
            )

            game_name = game["Name"]


            new_game_map[
                game_id
            ] = game_name


        # ---------------------
        # GAME_MAP更新
        # ---------------------

        GAME_MAP = new_game_map


        # ---------------------
        # ログ
        # ---------------------

        print(
            "===== GAME_MAP ====="
        )

        for game_id, game_name in GAME_MAP.items():

            print(
                f'"{game_id}": "{game_name}",'
            )

        print(
            "===================="
        )

        print(
            "✅ ゲーム一覧を更新しました"
        )


    except requests.RequestException as e:

        print(
            "❌ ゲーム一覧取得APIエラー:"
        )

        print(e)


    except (KeyError, TypeError, ValueError) as e:

        print(
            "❌ ゲーム一覧解析エラー:"
        )

        print(e)


    except Exception as e:

        print(
            "❌ ゲーム一覧取得エラー:"
        )

        print(e)


# =========================
# 起動時にゲーム一覧取得
# =========================

update_game_map()


# =========================
# utils
# =========================

def send_log(
    event_id,
    event_time,
    status
):

    try:

        res = requests.post(

            LOG_API_URL,

            json={
                "logs": [
                    {
                        "event_id": event_id,

                        "event_time": event_time,

                        "status_id": status
                    }
                ]
            },

            timeout=5
        )


        print(
            "LOG SEND:",
            "event_id=",
            event_id,
            "status=",
            status,
            "HTTP=",
            res.status_code,
            "response=",
            res.text
        )


    except Exception as e:

        print(
            "ログ送信エラー:",
            e
        )


# =========================
# Slack送信
# =========================

def send_slack():

    try:

        print(
            "📢 Slack送信開始"
        )

        print(
            "channel:",
            CHANNEL
        )

        print(
            "digital:",
            state.digital
        )

        print(
            "analog:",
            state.analog
        )


        response = slack_client.chat_postMessage(

            channel=CHANNEL,

            text="状態更新",

            blocks=[

                {
                    "type": "section",

                    "text": {
                        "type": "mrkdwn",

                        "text": f"🎮 {state.digital}"
                    }
                },

                {
                    "type": "section",

                    "text": {
                        "type": "mrkdwn",

                        "text": f"🃏 {state.analog}"
                    }
                }
            ]
        )


        print(
            "✅ Slack送信成功"
        )

        print(
            "Slack response:",
            response
        )


    except Exception as e:

        print(
            "❌ Slackエラー:"
        )

        print(
            type(e).__name__
        )

        print(
            e
        )


# =========================
# メンバー一覧取得
# =========================

def get_stayers():

    if (
        not STAYWATCH_API_URL
        or not STAYWATCH_API_KEY
    ):

        raise HTTPException(
            500,
            "環境変数が設定されていません"
        )


    try:

        res = requests.get(

            STAYWATCH_API_URL,

            headers={
                "X-API-Key": STAYWATCH_API_KEY
            },

            timeout=5
        )


        if res.status_code != 200:

            raise HTTPException(
                res.status_code,
                "外部APIエラー"
            )


        return res.json()


    except requests.RequestException as e:

        print(
            "🔥 requestsエラー:",
            e
        )

        raise HTTPException(
            500,
            f"外部API接続エラー: {e}"
        )


# =========================
# WebSocket
# =========================

clients = []


@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket
):

    await ws.accept()

    clients.append(ws)


    # ---------------------
    # 接続直後
    # ---------------------

    await ws.send_json({

        "analog": state.analog,

        "users": []
    })


    try:

        while True:

            await ws.receive_text()


    except WebSocketDisconnect:

        if ws in clients:

            clients.remove(ws)


# =========================
# WebSocket通知
# =========================

async def notify():

    users = []


    # ---------------------
    # analogプレイ中
    # ---------------------

    if state.analog != "何もしてない":

        try:

            loop = asyncio.get_event_loop()


            stayers = await loop.run_in_executor(
                None,
                get_stayers
            )


            users = [
                user["name"]
                for user in stayers
            ]


        except Exception as e:

            print(
                "stayers取得エラー:",
                e
            )

            users = []


    # ---------------------
    # 全クライアントへ送信
    # ---------------------

    for ws in clients:

        try:

            await ws.send_json({

                "analog": state.analog,

                "users": users
            })


        except Exception:

            pass


# =========================
# digital
# =========================

@app.post("/digital")
async def result(
    request: Request
):

    data = await request.json()


    # ---------------------
    # class_id取得
    # ---------------------

    try:

        class_id = int(
            data["class_id"]
        )

        now = datetime.now(
            JST
        ).isoformat()


    except Exception:

        raise HTTPException(
            422,
            "Invalid JSON"
        )


    # ---------------------
    # ID
    # ---------------------

    game_id = str(
        class_id
    )


    # ---------------------
    # ゲーム名取得
    # ---------------------

    new_digital = GAME_MAP.get(
        game_id,
        "不明"
    )


    print(
        "🎮 Digital:",
        game_id,
        new_digital
    )


    # ---------------------
    # ゲーム変更
    # ---------------------

    if game_id != state.last_digital_id:


        # -----------------
        # 前のゲーム終了
        # -----------------

        if state.last_digital_id is not None:

            send_log(
                state.last_digital_id,
                now,
                2
            )


        # -----------------
        # 新しいゲーム開始
        # -----------------

        send_log(
            game_id,
            now,
            1
        )


        # -----------------
        # 状態更新
        # -----------------

        state.last_digital_id = game_id
        state.digital = new_digital


        # -----------------
        # Slack
        # -----------------

        send_slack()


    return {

        "digital_status_id":
            game_id,

        "digital_status_name":
            state.digital
    }


# =========================
# analog
# =========================

@app.post("/analog")
async def analog(
    request: Request
):

    data = await request.json()


    # ---------------------
    # ID取得
    # ---------------------

    game_id = data.get(
        "analog_id"
    )


    if game_id is None:

        raise HTTPException(
            422,
            "Invalid JSON"
        )


    # ---------------------
    # 文字列に統一
    # ---------------------

    game_id = str(
        game_id
    )


    # ---------------------
    # APIに存在するか確認
    # ---------------------

    if game_id not in GAME_MAP:
        game_id = "0"


    # ---------------------
    # ゲーム名取得
    # ---------------------

    new_analog = GAME_MAP.get(
        game_id,
        "何もしてない"
    )


    now = datetime.now(
        JST
    ).isoformat()

    print(
        "🃏 Analog:",
        game_id,
        new_analog
    )

    # ---------------------
    # ゲーム変更
    # ---------------------

    if game_id != state.last_analog_id:

        # -----------------
        # 前のゲーム終了
        # -----------------

        if state.last_analog_id is not None:
            send_log(
                state.last_analog_id,
                now,
                2
            )

        # -----------------
        # 新しいゲーム開始
        # -----------------

        send_log(
            game_id,
            now,
            1
        )

        # -----------------
        # 状態更新
        # -----------------

        state.last_analog_id = game_id
        state.analog = new_analog

        # -----------------
        # Slack
        # -----------------

        send_slack()


        # -----------------
        # WebSocket通知
        # -----------------

        await notify()


    return {

        "analog_status_id":
            game_id,

        "analog_status_name":
            state.analog
    }

# =========================
# events
# =========================

@app.post("/events")
async def events(
    request: Request
):

    data = await request.json()


    if data.get(
        "type"
    ) == "url_verification":

        return {
            "challenge":
                data["challenge"]
        }

    return {
        "status": "ok"
    }