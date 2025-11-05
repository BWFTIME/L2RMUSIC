import asyncio
from pyrogram import Client, errors
from pyrogram.enums import ChatMemberStatus, ParseMode

import config

# Assuming this path is correct based on the traceback
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
        
        # Continuous loop to handle FloodWait errors during initial connection
        while True:
            try:
                # 1. Attempt to connect and log in
                await super().start()
                break  # Exit loop if connection is successful
                
            except errors.FloodWait as e:
                # Handle temporary flood wait by sleeping and retrying
                wait_time = e.value
                LOGGER(__name__).warning(
                    f"⚠️ Telegram FloodWait during login. Waiting for {wait_time} seconds before retrying..."
                )
                await asyncio.sleep(wait_time)
                
            except (ValueError, errors.AuthKeyUnregistered, errors.BotMethodInvalid, errors.BadRequest) as ex:
                # Handle fatal configuration errors (invalid token, API hash, etc.)
                LOGGER(__name__).error(
                    f"❌ Fatal Login Error! Please check your BOT_TOKEN, API_ID, and API_HASH.\n  Reason: {type(ex).__name__} - {ex}"
                )
                exit(1) # Exit application immediately on fatal error
                
            except Exception as ex:
                # Catch any other unexpected error during the start process
                LOGGER(__name__).error(
                    f"Bot failed to start due to an unexpected error: {type(ex).__name__} - {ex}"
                )
                exit(1)
        
        # --- POST-LOGIN SETUP ---
        
        # Set bot identity details
        self.id = self.me.id
        self.name = self.me.first_name + " " + (self.me.last_name or "")
        self.username = self.me.username
        self.mention = self.me.mention

        # 2. Check Logger/Log Channel Access and send startup message
        try:
            # Ensure this entire block is properly indented (4 spaces)
            await self.send_message(
                chat_id=config.LOGGER_ID,
                text=f"<u><b>» {self.mention} ʙᴏᴛ sᴛᴀʀᴛᴇᴅ :</b><u>\n\nɪᴅ : <code>{self.id}</code>\nɴᴀᴍᴇ : {self.name}\nᴜsᴇʀɴᴀᴍᴇ : @{self.username}",
            )
        except (errors.ChannelInvalid, errors.PeerIdInvalid):
            # Specific error handling for the log channel not being accessible
            LOGGER(__name__).error(
                "Bot has failed to access the log group/channel. Make sure that you have added your bot to your log group/channel."
            )
            exit(1)
        except Exception as ex:
            # General error handling for the log message failure
            LOGGER(__name__).error(
                f"Bot has failed to send startup message to the log group/channel.\n  Reason: {type(ex).__name__} - {ex}."
            )
            exit(1)

        # 3. Check for Admin status in log channel
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
            
        LOGGER(__name__).info(f"Music Bot Started as {self.name}")

    async def stop(self):
        LOGGER(__name__).info("Stopping Bot...")
        await super().stop()
