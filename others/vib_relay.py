# relay.py (运行在公网服务器，完全独立于机器人进程)
from fastapi import FastAPI, WebSocket
import uvicorn, json

app = FastAPI()
clients = set()

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True: await ws.receive_text()  # 保持心跳
    except: clients.remove(ws)

@app.get("/vib/{time}")  # 完全仿照原Flask路由
async def vib(time: int):
    if not clients: return {"status": "err", "msg": "内网设备离线"}
    # 转发给内网
    for c in clients.copy():
        await c.send_text(json.dumps({"time": time}))
    return {"status": "ok", "time": time}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=1145)  # 监听同一端口