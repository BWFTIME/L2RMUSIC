import asyncio  ### ❖ ➥ 𝗕𝐖𝗙 𝗠𝗨𝗦𝗜𝗖™🇮🇳
from datetime import datetime

from pyrogram.enums import ChatType

import config ### ❖ ➥ 𝗕𝐖𝗙 𝗠𝗨𝗦𝗜𝗖™🇮🇳
from L2RMUSIC import app
from L2RMUSIC.core.call import Ashish, autoend
from L2RMUSIC.utils.database import get_client, is_active_chat, is_autoend


async def auto_leave():    ### ❖ ➥ 𝗕𝐖𝗙 𝗠𝗨𝗦𝗜𝗖™🇮🇳
    if config.AUTO_LEAVING_ASSISTANT:
        while not await asyncio.sleep(900):
            from L2RMUSIC.core.userbot import assistants

            for num in assistants:
                client = await get_client(num)
                left = 0
                try:
                    async for i in client.get_dialogs():
                        if i.chat.type in [
                            ChatType.SUPERGROUP,
                            ChatType.GROUP,
                            ChatType.CHANNEL,
                        ]:
                            if (
                                i.chat.id != config.LOGGER_ID
                                and i.chat.id != -1001465277194
                                and i.chat.id != -1002120144597
                            ):
                                if left == 20:
                                    continue
                                if not await is_active_chat(i.chat.id):
                                    try:
                                        await client.leave_chat(i.chat.id)
                                        left += 1
                                    except:
                                        continue
                except:
                    pass


asyncio.create_task(auto_leave())


async def auto_end():    ### ❖ ➥ 𝗕𝐖𝗙 𝗠𝗨𝗦𝗜𝗖™🇮🇳
    while not await asyncio.sleep(5):
        ender = await is_autoend()
        if not ender:
            continue
        for chat_id in autoend:
            timer = autoend.get(chat_id)
            if not timer:
                continue
            if datetime.now() > timer:
                if not await is_active_chat(chat_id):
                    autoend[chat_id] = {}
                    continue
                autoend[chat_id] = {}
                try:
                    await Ashish.stop_stream(chat_id)
                except:
                    continue
                try:
                    await app.send_message(
                        chat_id,
                        "» ʙᴏᴛ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ʟᴇғᴛ ᴠɪᴅᴇᴏᴄʜᴀᴛ ʙᴇᴄᴀᴜsᴇ ɴᴏ ᴏɴᴇ ᴡᴀs ʟɪsᴛᴇɴɪɴɢ ᴏɴ ᴠɪᴅᴇᴏᴄʜᴀᴛ.",
                    )
                except:
                    continue                                 ### ❖ ➥ 𝗕𝐖𝗙 𝗠𝗨𝗦𝗜𝗖™🇮🇳


asyncio.create_task(auto_end())
