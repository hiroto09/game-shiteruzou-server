from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import HTMLResponse
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

GAME_MAP = {
    "0": "何もしてない"
}


# =========================
# FastAPI
# =========================

app = FastAPI()

JST = timezone(timedelta(hours=9))

# =========================
# IP制限設定
# =========================
# アクセスを許可するIPアドレスのリスト
ALLOWED_IPS = ["192.168.101.101", "202.15.17.104"]

@app.middleware("http")
async def ip_restriction_middleware(request: Request, call_next):
    # ▼ 修正ポイント: フロントエンド関連のURLパスのみIP制限の対象にする
    # 対象: ルートページ("/")、フロントエンド用API("/api/〜")、WebSocket("/ws")
    if request.url.path == "/" or request.url.path.startswith("/api/") or request.url.path == "/ws":
        
        # Nginxなどのリバースプロキシを経由している場合を考慮して X-Forwarded-For を確認
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else None

        # 許可リストに含まれていない場合は 403 Forbidden を返す
        if client_ip not in ALLOWED_IPS:
            print(f"🚨 拒否されたIPからのアクセス: {client_ip} (Path: {request.url.path})")
            return Response(content="Access Denied", status_code=403)
    
    # 対象外のパス（/analog, /digital, /events など）、または許可されたIPの場合はそのまま通す
    response = await call_next(request)
    return response


# =========================
# 状態管理 (ホストが全てを管理)
# =========================

class State:
    def __init__(self):
        # digital
        self.digital = "何もしてない"
        self.last_digital = None
        self.last_digital_id = None
        self.digital_start_time = None

        # analog
        self.analog = "何もしてない"
        self.last_analog_id = "0"
        self.analog_members = []
        self.analog_updated_at = None
        
        # inference status (ラズパイからの報告用)
        self.inference_running = False

state = State()


# =========================
# 初期化・API連携
# =========================

def update_game_map():
    global GAME_MAP
    try:
        print("🎮 ゲーム一覧をAPIから取得します")
        response = requests.get(EVENTS_API_URL, timeout=10)
        response.raise_for_status()

        games = response.json()["data"]
        new_game_map = {"0": "何もしてない"}

        for game in games:
            new_game_map[str(game["ID"])] = game["Name"]

        GAME_MAP = new_game_map
        print("✅ ゲーム一覧を更新しました")
    except Exception as e:
        print("❌ ゲーム一覧取得エラー:", e)

update_game_map()

def get_stayers():
    if not STAYWATCH_API_URL or not STAYWATCH_API_KEY:
        return []
    try:
        res = requests.get(
            STAYWATCH_API_URL,
            headers={"X-API-Key": STAYWATCH_API_KEY},
            timeout=5
        )
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print("🔥 staywatch APIエラー:", e)
    return []


# =========================
# ログ送信・Slack送信
# =========================

def send_log(event_id, event_time, status, members=None, room_users=None):
    if str(event_id) == "0":
        return

    try:
        # API仕様に合わせたJSON構造を作成
        log_data = {
            "event_id": str(event_id),
            "event_time": event_time,
            "status_id": int(status)
        }
        
        # メンバー指定があれば participate_users として追加
        if members is not None:
            # membersが文字列のリストになっている可能性を考慮し、API仕様(数値)に合わせる場合は適宜キャストが必要
            # 例: [int(m) for m in members] 
            log_data["participate_users"] = [int(m) for m in members]
        else:
            log_data["participate_users"] = []

        # room_users があれば追加 (今回は現状取得していないため空になる想定)
        if room_users is not None:
            log_data["room_users"] = [int(u) for u in room_users]
        else:
            log_data["room_users"] = []

        res = requests.post(LOG_API_URL, json={"logs": [log_data]}, timeout=5)
        print(f"LOG SEND: id={event_id} status={status} participants={log_data['participate_users']} HTTP={res.status_code}")
    except Exception as e:
        print("ログ送信エラー:", e)
        
        
def send_slack():
    try:
        slack_client.chat_postMessage(
            channel=CHANNEL,
            text="状態更新",
            blocks=[
                {"type": "section", "text": {"type": "mrkdwn", "text": f"🎮 {state.digital}"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"🃏 {state.analog}"}}
            ]
        )
    except Exception as e:
        print("❌ Slackエラー:", e)


# =========================
# WebSocket
# =========================

clients = []

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # WebSocketの初期接続もHTTPミドルウェアを通過するため、IP制限が機能します。
    await ws.accept()
    clients.append(ws)
    await ws.send_json({"analog": state.analog, "users": []})

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in clients:
            clients.remove(ws)

async def notify():
    users = []
    if state.analog != "何もしてない":
        try:
            loop = asyncio.get_event_loop()
            stayers = await loop.run_in_executor(None, get_stayers)
            # 現在のステータスに設定されているメンバーIDの人のみ抽出して名前を渡す
            users = [s["name"] for s in stayers if s["id"] in state.analog_members]
        except Exception as e:
            print("stayers取得エラー:", e)

    for ws in clients:
        try:
            await ws.send_json({"analog": state.analog, "users": users})
        except Exception:
            pass


# =========================
# アナログ状態統合変更処理
# =========================

async def handle_analog_change(new_id, new_members):
    new_id = str(new_id)
    if new_id not in GAME_MAP:
        new_id = "0"

    new_name = GAME_MAP.get(new_id, "何もしてない")
    now = datetime.now(JST).isoformat()
    changed = False

    # ゲームIDが変わった か、メンバーが変わった場合
    if new_id != state.last_analog_id or new_members != state.analog_members:
        # 古い状態の終了ログ
        if state.last_analog_id != "0":
            send_log(state.last_analog_id, now, 2, members=state.analog_members)

        # 新しい状態の開始ログ
        if new_id != "0":
            send_log(new_id, now, 1, members=new_members)

        # 状態更新
        state.last_analog_id = new_id
        state.analog = new_name
        state.analog_members = new_members
        state.analog_updated_at = now
        changed = True

    if changed:
        send_slack()
        await notify()


# =========================
# フロントエンド用エンドポイント
# =========================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(404, "index.html が見つかりません。")

@app.get("/api/status")
async def api_status():
    return {
        "confirmed": {
            "analog_id": state.last_analog_id,
            "game_name": state.analog,
            "updated_at": state.analog_updated_at
        },
        "selected_members": state.analog_members,
        "inference_running": state.inference_running
    }

@app.get("/api/members")
async def api_get_members():
    loop = asyncio.get_event_loop()
    stayers = await loop.run_in_executor(None, get_stayers)
    return {"members": [{"id": s["id"], "name": s["name"]} for s in stayers]}

@app.post("/api/members")
async def api_post_members(request: Request):
    data = await request.json()
    members = data.get("members", [])
    
    # メンバーが変わった場合、ログとSlackを自動処理
    await handle_analog_change(state.last_analog_id, members)
    return {"status": "ok", "selected_members": state.analog_members}


# =========================
# ラズパイ受信 (API /analog)
# =========================

@app.post("/analog")
async def analog_endpoint(request: Request):
    data = await request.json()

    if "inference_running" in data:
        state.inference_running = data["inference_running"]

    if "analog_id" in data:
        print(f"🃏 Raspi -> Analog ID: {data['analog_id']}")
        await handle_analog_change(data["analog_id"], state.analog_members)

    return {"status": "ok"}


# =========================
# 外部受信 (API /digital, /events)
# =========================

@app.post("/digital")
async def result(request: Request):
    data = await request.json()
    try:
        game_id = str(int(data["class_id"]))
        now = datetime.now(JST).isoformat()
    except Exception:
        raise HTTPException(422, "Invalid JSON")

    new_digital = GAME_MAP.get(game_id, "不明")

    if game_id != state.last_digital_id:
        if state.last_digital_id is not None and state.last_digital_id != "0":
            send_log(state.last_digital_id, now, 2)
        if game_id != "0":
            send_log(game_id, now, 1)

        state.last_digital_id = game_id
        state.digital = new_digital
        send_slack()

    return {"digital_status_id": game_id, "digital_status_name": state.digital}

@app.post("/events")
async def events(request: Request):
    data = await request.json()
    if data.get("type") == "url_verification":
        return {"challenge": data["challenge"]}
    return {"status": "ok"}