#!/usr/bin/bash

echo "设置环境变量"
source $HOME/.local/bin/env
source /root/AullBot/.env
export TZ='Asia/Shanghai'
echo "启动Napcat"
screen -dmS napcat bash -c "xvfb-run -a /root/Napcat/opt/QQ/qq --no-sandbox -q 3836808623"
sleep 5
echo "运行aullbot.main"
cd /root/AullBot/
uv run python -m aullbot.main