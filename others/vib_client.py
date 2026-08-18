# client.py (运行在内网Termux)
import asyncio, websockets, json, subprocess


async def loop():
    uri = "ws://183.66.27.22:42664/ws"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                print("隧道已打通")
                async for msg in ws:
                    data = json.loads(msg)
                    t = data["time"]
                    cty = data["chat_type"]
                    cty = "private" if cty else "group"
                    cid = data["chat_id"]
                    if 50 < t < 30000:
                        # 替换成🐺子的适配
                        subprocess.run(["termux-vibrate", "-d", str(t)])
                        print(
                            {
                                "status": "ok",
                                "time": t,
                                "chat_type": cty,
                                "chat_id": cid,
                            }
                        )
        except Exception as e:
            print(e)
            await asyncio.sleep(5)


asyncio.run(loop())
