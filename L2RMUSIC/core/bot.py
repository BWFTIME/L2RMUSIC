import asyncio
import os
from pyrogram import Client, errors
from pyrogram.enums import ChatMemberStatus, ParseMode

import config
from ..logging import LOGGER


class Ashish(Client):
    def __init__(self):
        LOGGER(__name__).info("Starting Bot...")
        super().__init__(
            name="L2RMUSIC",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            in_memory=True,
            parse_mode=ParseMode.HTML,
            max_concurrent_transmissions=7,
        )

    async def start(self):
        LOGGER(__name__).info("Attempting to connect to Telegram...")
        
        # Connect with retry on FloodWait
        while True:
            try:
                await super().start()
                break
            except errors.FloodWait as e:
                wait_time = e.value
                LOGGER(__name__).warning(
                    f"⚠️ Telegram FloodWait during login. Waiting for {wait_time} seconds before retrying..."
                )
                await asyncio.sleep(wait_time)
            except (ValueError, errors.AuthKeyUnregistered, errors.BotMethodInvalid, errors.BadRequest) as ex:
                LOGGER(__name__).error(
                    f"❌ Fatal Login Error! Please check your BOT_TOKEN, API_ID, and API_HASH.\n  Reason: {type(ex).__name__} - {ex}"
                )
                exit(1)
            except Exception as ex:
                LOGGER(__name__).error(
                    f"Bot failed to start due to an unexpected error: {type(ex).__name__} - {ex}"
                )
                exit(1)
        
        # Set bot identity
        self.id = self.me.id
        self.name = self.me.first_name + " " + (self.me.last_name or "")
        self.username = self.me.username
        self.mention = self.me.mention

        # ========== LOGGER_ID Handling ==========
        try:
            logger_id_raw = getattr(config, "LOGGER_ID", None)
            if logger_id_raw is None:
                logger_id_raw = os.environ.get("LOGGER_ID")
                if logger_id_raw is None:
                    raise ValueError("LOGGER_ID not set in config or env.")
            
            if isinstance(logger_id_raw, str):
                logger_id_raw = logger_id_raw.strip().strip('"').strip("'")
            
            LOGGER_ID = int(logger_id_raw)
            LOGGER(__name__).info(f"Using LOGGER_ID: {LOGGER_ID}")
        except (ValueError, TypeError) as e:
            LOGGER(__name__).error(
                f"❌ Invalid LOGGER_ID format: {logger_id_raw!r}. "
                "Please set a valid integer (e.g., -1001234567890) in config.py or env."
            )
            exit(1)

        # ========== Send Startup Message Robustly ==========
        try:
            LOGGER(__name__).info(f"Attempting to send startup message to LOGGER_ID: {LOGGER_ID}")
            
            await self.send_message(
                chat_id=LOGGER_ID,
                text=f"<u><b>» {self.mention} ʙᴏᴛ sᴛᴀʀᴛᴇᴅ :</b></u>\n\nɪᴅ : <code>{self.id}</code>\nɴᴀᴍᴇ : {self.name}\nᴜsᴇʀɴᴀᴍᴇ : @{self.username}",
            )
            LOGGER(__name__).info("✅ Startup message successfully sent to log group/channel.")
            
        except errors.PeerIdInvalid:
            LOGGER(__name__).error(
                f"❌ PeerIdInvalid Error: Bot is either not added to the log group/channel with ID {LOGGER_ID}, "
                "or the ID is wrong, OR the bot hasn't interacted with that group yet.\n"
                "👉 Solution: Make sure the bot is added to that group/channel as an admin."
            )
            exit(1)
        except Exception as ex:
            LOGGER(__name__).error(
                f"❌ Failed to send startup message to log group/channel.\n  Reason: {type(ex).__name__} - {ex}."
            )
            exit(1)

        # ========== Check Admin Status Safely ==========
        try:
            a = await self.get_chat_member(LOGGER_ID, self.id)
            if a.status != ChatMemberStatus.ADMINISTRATOR:
                LOGGER(__name__).error(
                    "❌ Bot is not an admin in the log group/channel. Please promote it."
                )
                exit(1)
        except Exception as ex:
            LOGGER(__name__).warning(
                f"⚠️ Could not verify admin status directly (Non-critical): {ex}"
            )

        # ========== Cache Channel Resolution (Optional) ==========
        try:
            if hasattr(config, 'CACHE_CHANNEL_ID'):
                cache_chat_id = int(config.CACHE_CHANNEL_ID)
            else:
                cache_chat_id = int(os.environ.get("CACHE_CHANNEL_ID", 0))
                if cache_chat_id == 0:
                    raise ValueError("CACHE_CHANNEL_ID not set")

            await self.get_chat(cache_chat_id)
            LOGGER(__name__).info(f"✅ Cache channel resolved: {cache_chat_id}")
        except Exception as e:
            LOGGER(__name__).warning(f"⚠️ Cache channel issue (non-critical): {e}")

        LOGGER(__name__).info(f"🎵 Music Bot Started as {self.name}")

    async def stop(self):
        LOGGER(__name__).info("Stopping Bot...")
        await super().stop()
                LOGGER(__name__).error(
                    "❌ Bot is not an admin in the log group/channel. Please promote it."
                )
                exit(1)
        except Exception as ex:
            LOGGER(__name__).error(
                f"❌ Failed to check bot's admin status.\n  Reason: {type(ex).__name__} - {ex}."
            )
            exit(1)

        # ========== Cache channel resolution (optional) ==========
        try:
            if hasattr(config, 'CACHE_CHANNEL_ID'):
                cache_chat_id = int(config.CACHE_CHANNEL_ID)
            else:
                cache_chat_id = int(os.environ.get("CACHE_CHANNEL_ID", 0))
                if cache_chat_id == 0:
                    raise ValueError("CACHE_CHANNEL_ID not set")

            await self.get_chat(cache_chat_id)
            LOGGER(__name__).info(f"✅ Cache channel resolved: {cache_chat_id}")
        except Exception as e:
            LOGGER(__name__).warning(f"⚠️ Cache channel issue (non-critical): {e}")

        LOGGER(__name__).info(f"🎵 Music Bot Started as {self.name}")

    async def stop(self):
        LOGGER(__name__).info("Stopping Bot...")
        await super().stop()
