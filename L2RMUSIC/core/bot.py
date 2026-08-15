# All rights reserved.
#

import sys
import os
from pyrogram import Client, errors
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

import config

from ..logging import LOGGER


class AyuBot(Client):
    def __init__(self):
        LOGGER(__name__).info(f"Starting Bot")
        super().__init__(
            "L2RMUSIC",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            in_memory=True,
        )

    async def start(self):
        await super().start()
        get_me = await self.get_me()
        self.username = get_me.username
        self.id = get_me.id
        self.name = get_me.first_name + " " + (get_me.last_name or "")
        self.mention = self.me.mention

        # ========== Safe Logger ID Processing & Startup Message ==========
        try:
            logger_id_raw = getattr(config, "LOGGER_ID", None)
            if logger_id_raw is None:
                logger_id_raw = os.environ.get("LOGGER_ID")
            
            if logger_id_raw:
                if isinstance(logger_id_raw, str):
                    logger_id_raw = logger_id_raw.strip().strip('"').strip("'")
                LOGGER_ID = int(logger_id_raw)
            else:
                LOGGER_ID = None

            if LOGGER_ID:
                try:
                    await self.get_chat(LOGGER_ID)
                except Exception:
                    pass

                await self.send_message(
                    LOGGER_ID,
                    text=f"<u><b>{self.mention} ʙᴏᴛ sᴛᴀʀᴛᴇᴅ :</b></u>\n\nɪᴅ : <code>{self.id}</code>\nɴᴀᴍᴇ : {self.name}\nᴜsᴇʀɴᴀᴍᴇ : @{self.username}",
                )
                LOGGER(__name__).info("✅ Startup message sent to log group successfully.")
            else:
                LOGGER(__name__).warning("⚠️ LOGGER_ID is not set in config or environment variables.")

        except errors.PeerIdInvalid:
            LOGGER(__name__).error(
                "❌ PeerIdInvalid: The bot is not a member of the log group or the LOGGER_ID is incorrect. "
                "Make sure the bot is added to your log group and promoted as an admin!"
            )
        except Exception as ex:
            LOGGER(__name__).error(
                f"Bot has failed to access the log Group.\n  Reason: {type(ex).__name__} - {ex}"
            )

        # ========== Set Bot Commands ==========
        if getattr(config, "SET_CMDS", "True") == str(True):
            try:
                await self.set_bot_commands(
                    commands=[
                        BotCommand("start", "sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ"),
                        BotCommand("help", "ɢᴇᴛ ᴛʜᴇ ʜᴇʟᴘ ᴍᴇɴᴜ"),
                        BotCommand("ping", "ᴄʜᴇᴄᴋ ʙᴏᴛ ɪs ᴀʟɪᴠᴇ ᴏʀ ᴅᴇᴀᴅ"),
                    ],
                    scope=BotCommandScopeAllPrivateChats(),
                )
                await self.set_bot_commands(
                    commands=[
                        BotCommand("play", "sᴛᴀʀᴛ ᴘʟᴀʏɪɴɢ ʀᴇǫᴜᴇsᴛᴇᴅ sᴏɴɢ"),
                    ],
                    scope=BotCommandScopeAllGroupChats(),
                )
                await self.set_bot_commands(
                    commands=[
                        BotCommand("play", "sᴛᴀʀᴛ ᴘʟᴀʏɪɴɢ ʀᴇǫᴜᴇsᴛᴇᴅ sᴏɴɢ"),
                        BotCommand("skip", "ᴍᴏᴠᴇ ᴛᴏ ɴᴇxᴛ ᴛʀᴀᴄᴋ ɪɴ ǫᴜᴇᴜᴇ"),
                        BotCommand("pause", "ᴘᴀᴜsᴇ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴘʟᴀʏɪɴɢ sᴏɴɢ"),
                        BotCommand("resume", "ʀᴇsᴜᴍᴇ ᴛʜᴇ ᴘᴀᴜsᴇᴅ sᴏɴɢ"),
                        BotCommand("end", "ᴄʟᴇᴀʀ ᴛʜᴇ ǫᴜᴇᴜᴇ ᴀᴍᴅ ʟᴇᴀᴠᴇ ᴠᴏɪᴄᴇᴄʜَات"),
                        BotCommand("shuffle", "ʀᴀɴᴅᴏᴍʟʏ sʜᴜғғʟᴇs ᴛʜᴇ ǫᴜᴇᴜᴇᴅ ᴘʟᴀʏʟɪsᴛ."),
                        BotCommand(
                            "playmode",
                            "ᴀʟʟᴏᴡs ʏᴏᴜ ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇ ᴅᴇғᴀᴜʟᴛ ᴘʟᴀʏᴍᴏᴅᴇ ғᴏʀ ʏᴏᴜʀ ᴄʜᴀᴛ",
                        ),
                        BotCommand(
                            "settings",
                            "ᴏᴘᴇɴ ᴛʜᴇ sᴇᴛᴛɪɴɢs ᴏғ ᴛʜᴇ ᴍᴜsɪᴄ ʙᴏᴛ ғᴏʀ ʏᴏᴜʀ ᴄʜᴀᴛ.",
                        ),
                    ],
                    scope=BotCommandScopeAllChatAdministrators(),
                )
            except Exception:
                pass

        # ========== Admin Status Check in Logger Group ==========
        try:
            if LOGGER_ID:
                a = await self.get_chat_member(LOGGER_ID, self.id)
                if a.status != ChatMemberStatus.ADMINISTRATOR:
                    LOGGER(__name__).warning("⚠️ Warning: Bot is not an admin in the Logger Group!")
        except Exception:
            pass

        if get_me.last_name:
            self.name = get_me.first_name + " " + get_me.last_name
        else:
            self.name = get_me.first_name

        LOGGER(__name__).info(f"MusicBot Started as {self.name}")

    async def stop(self):
        LOGGER(__name__).info("Stopping Bot...")
        await super().stop()
