import asyncio
from pyrogram import Client, errors
from pyrogram.enums import ChatMemberStatus, ParseMode

# ✅ ABSOLUTE import – config.py root par hai
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
        
        self.id = self.me.id
        self.name = self.me.first_name + " " + (self.me.last_name or "")
        self.username = self.me.username
        self.mention = self.me.mention

        try:
            await self.send_message(
                chat_id=config.LOGGER_ID,
                text=f"<u><b>» {self.mention} ʙᴏᴛ sᴛᴀʀᴛᴇᴅ :</b><u>\n\nɪᴅ : <code>{self.id}</code>\nɴᴀᴍᴇ : {self.name}\nᴜsᴇʀɴᴀᴍᴇ : @{self.username}",
            )
        except (errors.ChannelInvalid, errors.PeerIdInvalid):
            LOGGER(__name__).error(
                "Bot has failed to access the log group/channel. Make sure that you have added your bot to your log group/channel."
            )
            exit(1)
        except Exception as ex:
            LOGGER(__name__).error(
                f"Bot has failed to send startup message to the log group/channel.\n  Reason: {type(ex).__name__} - {ex}."
            )
            exit(1)

        try:
            a = await self.get_chat_member(config.LOGGER_ID, self.id)
            if a.status != ChatMemberStatus.ADMINISTRATOR:
                LOGGER(__name__).error(
                    "Please promote your bot as an admin in your log group/channel."
                )
                exit(1)
        except Exception as ex:
            LOGGER(__name__).error(
                f"Failed to check bot's admin status in the log group/channel.\n  Reason: {type(ex).__name__} - {ex}."
            )
            exit(1)

        # Cache channel resolve
        try:
            if hasattr(config, 'CACHE_CHANNEL_ID'):
                cache_chat_id = int(config.CACHE_CHANNEL_ID)
            else:
                import os
                cache_chat_id = int(os.environ.get("CACHE_CHANNEL_ID", 0))
                if cache_chat_id == 0:
                    raise ValueError("CACHE_CHANNEL_ID not set")

            await self.get_chat(cache_chat_id)
            LOGGER(__name__).info(f"✅ Cache channel resolved: {cache_chat_id}")

        except AttributeError:
            LOGGER(__name__).warning("⚠️ CACHE_CHANNEL_ID not defined in config. Skipping pre-resolution.")
        except ValueError:
            LOGGER(__name__).error("❌ CACHE_CHANNEL_ID is invalid or not set. Please set it in config or as env variable.")
        except Exception as e:
            LOGGER(__name__).error(f"❌ Failed to resolve cache channel: {e}")
            LOGGER(__name__).error("   Make sure the bot is a member of that channel and the ID is correct.")

        LOGGER(__name__).info(f"Music Bot Started as {self.name}")

    async def stop(self):
        LOGGER(__name__).info("Stopping Bot...")
        await super().stop()
