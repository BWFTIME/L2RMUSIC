import asyncio
from datetime import datetime
from pyrogram.enums import ChatType
import config
from L2RMUSIC import app
from L2RMUSIC.core.call import Ashish, autoend
from L2RMUSIC.utils.database import get_client, is_active_chat, is_autoend

async def auto_leave():
    if config.AUTO_LEAVING_ASSISTANT:
        while True:
            await asyncio.sleep(900)  # Sleep for 15 minutes (900 seconds)
            from L2RMUSIC.core.userbot import assistants

            for num in assistants:
                client = await get_client(num)
                left = 0
                try:
                    async for i in client.get_dialogs():
                        if i.chat.type in [ChatType.SUPERGROUP, ChatType.GROUP, ChatType.CHANNEL]:
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
                                    except Exception as e:
                                        print(f"Error leaving chat {i.chat.id}: {e}")
                                        continue
                except Exception as e:
                    print(f"Error in auto_leave for assistant {num}: {e}")

asyncio.create_task(auto_leave())

async def auto_end():
    while True:
        await asyncio.sleep(5)  # Sleep for 5 seconds between checks
        ender = await is_autoend()
        if not ender:
            continue
        for chat_id in autoend:
            timer = autoend.get(chat_id)
            if not timer:
                continue
            if datetime.now() > timer:
                if not await is_active_chat(chat_id):
                    autoend[chat_id] = {}  # Reset the autoend timer
                    continue
                autoend[chat_id] = {}  # Reset the autoend timer
                try:
                    await Ashish.stop_stream(chat_id)
                except Exception as e:
                    print(f"Error stopping stream for chat {chat_id}: {e}")
                    continue
                try:
                    await app.send_message(
                        chat_id,
                        "» ʙᴏᴛ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ʟᴇғᴛ ᴠɪᴅᴇᴏᴄʜᴀᴛ ʙᴇᴄᴀᴜsᴇ ɴᴏ ᴏɴᴇ ᴡᴀs ʟɪsᴛᴇɴɪɴɢ ᴏɴ ᴠɪᴅᴇᴏᴄʜᴀᴛ.",
                    )
                except Exception as e:
                    print(f"Error sending message to chat {chat_id}: {e}")
                    continue

asyncio.create_task(auto_end())
