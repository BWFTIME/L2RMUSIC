import asyncio
import importlib
import os

from pyrogram import idle
from pytgcalls.exceptions import NoActiveGroupCall

import config
from L2RMUSIC import LOGGER, app, userbot
from L2RMUSIC.core.call import Ashish
from L2RMUSIC.core.dir import dirr          # ✅ Import kiya
from L2RMUSIC.misc import sudo
from L2RMUSIC.plugins import ALL_MODULES
from L2RMUSIC.utils.database import get_banned_users, get_gbanned
from config import BANNED_USERS


async def init():
    if (
        not config.STRING1
        and not config.STRING2
        and not config.STRING3
        and not config.STRING4
        and not config.STRING5
    ):
        LOGGER(__name__).error("♦️ 𝐒𝐭𝐫𝐢𝐧𝐠 𝐒𝐞𝐬𝐬𝐢𝐨𝐧 𝐍𝐨𝐭 𝐅𝐢𝐥𝐥𝐞𝐝, 𝐏𝐥𝐞𝐚𝐬𝐞 𝐅𝐢𝐥𝐥 𝐀 𝐏𝐲𝐫𝐨𝐠𝐫𝐚𝐦 𝐒𝐞𝐬𝐬𝐢𝐨𝐧 🍃...")
        exit()

    # ✅ Sabse pehle folders create karo (downloads, cache, etc.)
    dirr()  # Ye function sync hai, isliye await nahi lagana

    # Run sudo method to initialize required configurations
    await sudo()

    # Load banned users
    try:
        users = await get_gbanned()
        for user_id in users:
            BANNED_USERS.add(user_id)

        users = await get_banned_users()
        for user_id in users:
            BANNED_USERS.add(user_id)
    except Exception as e:
        LOGGER(__name__).error(f"Error loading banned users: {str(e)}")

    # Start the app and userbot
    await app.start()

    # Dynamically load all modules
    for all_module in ALL_MODULES:
        importlib.import_module("L2RMUSIC.plugins" + all_module)

    LOGGER("L2RMUSIC.plugins").info("👻 𝐀𝐥𝐥 𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐋𝐨𝐚𝐝𝐞𝐝 𝐁𝐚𝐛𝐲❣️...")

    # Start userbot and call handler
    await userbot.start()
    await Ashish.start()

    # ❌ DUMMY STREAM CALL HATAYA (kyonki ye URL dead hai aur error deta hai)
    # Agar fir bhi kuch stream karna hai toh valid URL daalein, warna hata dena better hai.

    # Start decorators (event handlers)
    await Ashish.decorators()

    LOGGER("L2RMUSIC").info("╔═════ஜ۩۞۩ஜ════╗\n  ༄𝐿 2 𝙍.🖤🜲𝐾𝐼𝐍𝐺❦︎ 𝆺𝅥⃝🍷\n╚═════ஜ۩۞۩ஜ════╝")

    # Bot ko idle mode mein rakho
    await idle()

    # Clean shutdown
    await app.stop()
    await userbot.stop()
    LOGGER("L2RMUSIC").info("✨𝗦𝗧𝗢𝗣 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖🎻 𝗕𝗢𝗧🍒...")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(init())
