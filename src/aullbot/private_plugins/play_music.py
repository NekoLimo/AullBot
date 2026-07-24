# scr/aullbot/private_plugins/play_music.py
import tqdm
import os
import requests
from .. import context
from .command_registry import command


def Todo(*args): 
    """占位符"""
    return "todo bro😭"


async def send_message(text=None, file=None):
    bot = context.get_bot()
    chat_type = context.get_chat_type()
    chat_id = context.get_chat_id()
    if chat_type == 0:  # group
        if text:
            await bot.api.qq.post_group_msg(group_id=chat_id, text=text)
            print("group:", text)
        elif file:
            await bot.api.qq.send_group_record(group_id=chat_id, file=file)
            print("group:", file)
    elif chat_type == 1:  # private
        if text:
            await bot.api.qq.post_private_msg(user_id=chat_id, text=text)
            print("private:", text)
        elif file:
            await bot.api.qq.send_private_record(user_id=chat_id, file=file)
            print("private:", file)


@command("/music")
async def play_music(song_name: str) -> None | str | int:
    """
    使用网易云网页版音乐API
    这个神秘API我也没太搞懂
    无法下载收费/会员音乐
    使用方法
    @机器人 music 歌曲名 -作者(作者可选)
    例子:@一只小null喵~ music hello -omfg
    默认只下载最接近的歌曲。
    """

    if not song_name:
        return """使用网易云网页版音乐API
这个神秘API我也没太搞懂
无法下载收费/会员音乐
使用方法
@机器人 music 歌曲名 -作者(作者可选)
例子:@一只小null喵~ music hello -omfg
默认只下载最接近的歌曲。"""

    url = "http://music.163.com/api/search/get/web"
    params = {
        "csrf_token": "",
        "hlpretag": "",
        "hlposttag": "",
        "s": song_name,
        "type": 1,
        "offset": 0,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://music.163.com/",
        "Origin": "https://music.163.com",
    }

    print("请求歌曲列表")
    response = requests.get(url, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    print("完成")

    print("解析歌曲ID")
    if data.get("code") == 200:
        songs = data.get("result", {}).get("songs", [])

        if not songs:
            await send_message(text="未找到歌曲")

        song_list_string = ""
        for idx, song in enumerate(songs, start=1):
            song_id = song.get("id")
            name = song.get("name")
            artists = ", ".join(
                artist.get("name", "") for artist in song.get("artists", [])
            )
            fee = song.get("fee")
            # print(f"{idx}. {name} - {artists} (ID: {song_id}, fee: {fee})")
            song_list_string = (
                song_list_string
                + f"{idx}. {name} - {artists} (ID: {song_id}, fee: {fee})\n"
            )
        song_list_string = song_list_string.rstrip("\n")

        await send_message(text=song_list_string)

        song_id = data["result"]["songs"][0]["id"]

        await send_message(text="下载第一项")

    else:
        await send_message(text=f"请求失败 {data.get('code')}")
        return -1

    print("开始下载")
    url = f"http://music.163.com/song/media/outer/url?id={song_id}.mp3"
    response = requests.get(url, stream=True)

    # 获取文件大小（字节），如果服务器返回了 Content-Length
    total_size = int(response.headers.get("content-length", 0))

    illegal_character = "\\/:*?\"<>|' "
    for i in illegal_character:
        if i in song_name:
            song_name = song_name.replace(i, "_")

    # 使用 tqdm 创建进度条
    with open(os.path.join(context.get_cache_path(), f"{song_name}.mp3"), "wb") as f:
        # 如果 total_size 为 0，则进度条不显示总量（仅显示已下载量）
        with tqdm.tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            desc=f"下载 {song_name}.mp3",
            disable=total_size == 0,  # 如果大小未知，也可显示，这里保留显示
        ) as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # 过滤掉 keep-alive 的空块
                    f.write(chunk)
                    pbar.update(len(chunk))
    try:
        await send_message(file=os.path.join(context.get_cache_path(), f"{song_name}.mp3"))
    except Exception as e:
        return f"{e} (可能下载了会员歌曲)"
    return None
