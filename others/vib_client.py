# client.py (运行在内网Termux)
import asyncio, websockets, json, subprocess

async def loop():
    uri = "ws://你的公网IP:8000/ws"  # 注意端口，中继的WS端口
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print("隧道已打通")
                async for msg in ws:
                    data = json.loads(msg)
                    t = data["time"]
                    if 50 < t < 30000:
                        subprocess.run(['termux-vibrate', '-d', str(t)])
        except: await asyncio.sleep(5)

asyncio.run(loop())