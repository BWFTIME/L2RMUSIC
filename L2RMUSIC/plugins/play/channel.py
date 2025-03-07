from pyrogram import filters
from pyrogram.enums import ChatMembersFilter, ChatMemberStatus, ChatType
from pyrogram.types import Message

from L2RMUSIC import app
from L2RMUSIC.utils.database import set_cmode
from L2RMUSIC.utils.decorators.admins import AdminActual
from config import BANNED_USERS

@app.on_message(filters.command(["channelplay"]) & filters.group & ~BANNED_USERS)
@AdminActual
async def playmode_(client, message: Message, _):
    if len(message.command) < 2:
        return await message.reply_text(_["cplay_1"].format(message.chat.title))
    
    query = message.text.split(None, 2)[1].lower().strip()

    if query == "disable":
        await set_cmode(message.chat.id, None)
        return await message.reply_text(_["cplay_7"])

    elif query == "linked":
        chat = await app.get_chat(message.chat.id)
        if chat.linked_chat:
            chat_id = chat.linked_chat.id
            await set_cmode(message.chat.id, chat_id)
            return await message.reply_text(
                _["cplay_3"].format(chat.linked_chat.title, chat.linked_chat.id)
            )
        else:
            return await message.reply_text(_["cplay_2"])

    else:
        try:
            chat = await app.get_chat(query)
        except Exception:
            return await message.reply_text(_["cplay_4"])

        if chat.type != ChatType.CHANNEL:
            return await message.reply_text(_["cplay_5"])

        try:
            admin = None
            async for user in app.get_chat_members(chat.id, filter=ChatMembersFilter.ADMINISTRATORS):
                if user.status == ChatMemberStatus.OWNER:
                    admin = user.user
                    break
            if not admin:
                return await message.reply_text(_["cplay_4"])

            if admin.id != message.from_user.id:
                return await message.reply_text(_["cplay_6"].format(chat.title, admin.username))

        except Exception:
            return await message.reply_text(_["cplay_4"])

        await set_cmode(message.chat.id, chat.id)
        return await message.reply_text(_["cplay_3"].format(chat.title, chat.id))
