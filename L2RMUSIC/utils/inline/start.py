from pyrogram.types import InlineKeyboardButton

import config
from L2RMUSIC import app


def start_panel(_):
    buttons = [
        [
            InlineKeyboardButton(
                text=_["S_B_1"], url=f"https://t.me/{app.username}?startgroup=true"
            ),
            InlineKeyboardButton(text=_["S_B_2"], url=config.SUPPORT_CHAT),
        ],
    ]
    return buttons


def private_panel(_):
    buttons = [
        [
            InlineKeyboardButton(
                text="⛩️ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ⛩️",
                url=f"https://t.me/{app.username}?startgroup=true"
            )
        ],
        [
            InlineKeyboardButton(text="👑 ᴏᴡɴᴇʀ 👑", user_id=config.OWNER_ID),
            InlineKeyboardButton(text="🍒‌⃰‌ᴄʜᴀɴɴᴇʟ⏎‌🝛꯭🧸", url=config.SUPPORT_CHANNEL),
        ],
        [
            InlineKeyboardButton(
                text="🍧ʜᴇʟᴩ🍧",
                callback_data="settings_helper"
            )
        ],
    ]
    return buttons
