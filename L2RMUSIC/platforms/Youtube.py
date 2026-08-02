import asyncio
import os
import re
from typing import Union, Optional
import aiohttp
import aiofiles
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch, CustomSearch
from L2RMUSIC import LOGGER, app 
from L2RMUSIC.utils.formatters import time_to_seconds
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIG ---
YT_API_KEY = "30DxNexGenBots0055e5"
YTPROXY = "https://tgapi.xbitcode.com"
PLAYLIST_ID = -1003616869403   # <-- Ensure bot is admin here
MONGO_DB_URI = "mongodb+srv://L2RKING:BWF_MUSIC1@l2rking.1ikcd.mongodb.net/?retryWrites=true&w=majority"
LIMIT_SECONDS = 900

# --- FALLBACK API ---
YOUR_API_URL = None
FALLBACK_API_URL = "https://shrutibots.site"

logger = LOGGER(__name__)

# --- DATABASE ---
_mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
mongodb = _mongo_async_.L2RMUSIC
trackdb = mongodb.track_cache

# --- LOAD FALLBACK URL ---
async def load_api_url():
    global YOUR_API_URL
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://pastebin.com/raw/rLsBhAQa", timeout=10) as resp:
                if resp.status == 200:
                    YOUR_API_URL = (await resp.text()).strip()
                    logger.info(f"Fallback API URL loaded: {YOUR_API_URL}")
                else:
                    YOUR_API_URL = FALLBACK_API_URL
    except Exception:
        YOUR_API_URL = FALLBACK_API_URL

try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(load_api_url())
    else:
        loop.run_until_complete(load_api_url())
except RuntimeError:
    pass

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        self.upload_retries = 3  # Number of retries for upload

    # ---------- LOCAL FILE HELPERS ----------
    def _find_file(self, vid_id: str) -> Optional[str]:
        if not os.path.exists("downloads"):
            return None
        for ext in ("m4a", "mp4", "mp3", "webm"):
            path = f"downloads/{vid_id}.{ext}"
            if os.path.exists(path) and os.path.getsize(path) > 2048:
                return os.path.abspath(path)
            elif os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
        return None

    async def _download_from_file_id(self, file_id: str, output_path: str) -> Optional[str]:
        try:
            file = await app.download_media(file_id, file_name=output_path)
            if file and os.path.exists(file) and os.path.getsize(file) > 2048:
                return file
        except Exception as e:
            logger.error(f"Download from file_id failed: {e}")
        return None

    # ---------- CACHE UPLOAD (with retries) ----------
    async def _upload_to_cache(self, vid_id: str, file_path: str, title: str, is_video: bool):
        """Upload file to channel and store file_id in DB with retry logic."""
        if not os.path.exists(file_path):
            logger.error(f"File not found for upload: {file_path}")
            return False

        db_id = f"{vid_id}_video" if is_video else vid_id

        # Check if already cached (avoid duplicate uploads)
        try:
            existing = await trackdb.find_one({"vid_id": db_id})
            if existing and "file_id" in existing:
                logger.info(f"Already cached: {title}")
                return True
        except Exception as e:
            logger.warning(f"DB check failed: {e}")

        for attempt in range(1, self.upload_retries + 1):
            try:
                logger.info(f"📤 Uploading to Channel (attempt {attempt}/{self.upload_retries}): {title}")
                cap = f"**Song:** {title}\n**ID:** `{vid_id}`\n**Saved by:** {app.me.mention}"

                if is_video:
                    msg = await app.send_video(PLAYLIST_ID, file_path, caption=cap, supports_streaming=True)
                else:
                    msg = await app.send_audio(PLAYLIST_ID, file_path, caption=cap, title=title)

                if msg:
                    file_id = None
                    if is_video and msg.video:
                        file_id = msg.video.file_id
                    elif not is_video and msg.audio:
                        file_id = msg.audio.file_id
                    elif msg.document:
                        file_id = msg.document.file_id

                    if file_id:
                        await trackdb.update_one(
                            {"vid_id": db_id},
                            {
                                "$set": {
                                    "file_id": file_id,
                                    "title": title,
                                    "type": "video" if is_video else "audio"
                                }
                            },
                            upsert=True
                        )
                        logger.info(f"✅ Cached successfully: {title} (file_id: {file_id[:20]}...)")
                        return True
                    else:
                        logger.warning("Upload succeeded but no file_id found.")
                else:
                    logger.warning("Upload returned no message.")

            except Exception as e:
                logger.error(f"Upload attempt {attempt} failed: {e}")
                if attempt < self.upload_retries:
                    await asyncio.sleep(2)  # wait before retry
                else:
                    logger.error(f"All upload attempts failed for {title}")

        return False

    # ---------- RETRIEVE CACHED FILE ----------
    async def get_cached_file(self, vid_id: str, is_video: bool = False) -> Optional[str]:
        db_id = f"{vid_id}_video" if is_video else vid_id

        # 1. Local file
        local_path = self._find_file(vid_id)
        if local_path:
            return local_path

        # 2. DB file_id
        try:
            doc = await trackdb.find_one({"vid_id": db_id})
            if doc and "file_id" in doc:
                file_id = doc["file_id"]
                output_path = os.path.join("downloads", f"{vid_id}.mp4")
                os.makedirs("downloads", exist_ok=True)
                downloaded = await self._download_from_file_id(file_id, output_path)
                if downloaded:
                    return downloaded
                else:
                    # invalid file_id, remove from DB
                    await trackdb.delete_one({"vid_id": db_id})
                    logger.warning(f"Removed invalid cached entry for {vid_id}")
        except Exception as e:
            logger.error(f"Cache retrieval DB error: {e}")

        return None

    # ---------- API CALLS ----------
    async def get_api_url(self, vid_id: str, is_video: bool) -> Optional[str]:
        try:
            if not YT_API_KEY or not YTPROXY:
                return None
            headers = {"x-api-key": YT_API_KEY}
            async with aiohttp.ClientSession() as session:
                url = f"{YTPROXY}/info/{vid_id}"
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    if data.get("status") != "success":
                        return None
                    return data.get("video_url") if is_video else data.get("audio_url")
        except Exception as e:
            logger.error(f"Primary API error: {e}")
            return None

    async def _external_api_download(self, vid_id: str, is_video: bool) -> Optional[str]:
        global YOUR_API_URL
        if not YOUR_API_URL:
            await load_api_url()
        current_api = YOUR_API_URL or FALLBACK_API_URL

        ext = "mp4" if is_video else "mp3"
        file_path = os.path.join("downloads", f"{vid_id}.{ext}")
        os.makedirs("downloads", exist_ok=True)

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Get token
                params = {"url": vid_id, "type": "video" if is_video else "audio"}
                async with session.get(f"{current_api}/download", params=params, timeout=60) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    token = data.get("download_token")
                    if not token:
                        return None

                # Step 2: Stream file
                stream_url = f"{current_api}/stream/{vid_id}?type={'video' if is_video else 'audio'}"
                headers = {"X-Download-Token": token}
                async with session.get(stream_url, headers=headers, timeout=600 if is_video else 300) as resp:
                    if resp.status != 200:
                        return None
                    async with aiofiles.open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(16384):
                            await f.write(chunk)

                if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                    return file_path
        except Exception as e:
            logger.error(f"Fallback API download failed: {e}")
        return None

    # ---------- MAIN DOWNLOAD (NOW SYNC CACHING) ----------
    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> tuple:
        """
        Returns: (file_path, is_cached) 
        Now it ensures the file is downloaded and cached before returning.
        """
        # Extract video ID
        if videoid:
            vid_id = link
            link = self.base + link
        else:
            if "v=" in link:
                vid_id = link.split('v=')[-1].split('&')[0]
            else:
                vid_id = link.split('/')[-1]

        is_video_request = bool(video or songvideo)
        title = title or vid_id

        # 1. Check cache
        cached_path = await self.get_cached_file(vid_id, is_video_request)
        if cached_path:
            logger.info(f"✅ Cache hit: {title}")
            return cached_path, True

        # 2. Try primary API: download and upload
        logger.info(f"🔄 Attempting primary download for {title}")
        try:
            direct_url = await self.get_api_url(vid_id, is_video_request)
            if direct_url:
                # Download the file using the direct URL
                file_path = os.path.join("downloads", f"{vid_id}.mp4")
                os.makedirs("downloads", exist_ok=True)
                async with aiohttp.ClientSession() as session:
                    async with session.get(direct_url) as resp:
                        if resp.status == 200:
                            async with aiofiles.open(file_path, "wb") as f:
                                async for chunk in resp.content.iter_chunked(1048576):
                                    await f.write(chunk)
                            if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                                # Upload to channel
                                uploaded = await self._upload_to_cache(vid_id, file_path, title, is_video_request)
                                if uploaded:
                                    return file_path, True
                                else:
                                    # Upload failed but we have the file, still return it
                                    logger.warning("Upload failed, but returning local file.")
                                    return file_path, True
                            else:
                                logger.error("Primary download produced invalid file.")
        except Exception as e:
            logger.error(f"Primary download failed: {e}")

        # 3. Fallback: external API download
        logger.warning(f"⚠️ Switching to fallback API for {vid_id}")
        fallback_file = await self._external_api_download(vid_id, is_video_request)
        if fallback_file:
            # Upload to cache
            uploaded = await self._upload_to_cache(vid_id, fallback_file, title, is_video_request)
            if uploaded:
                return fallback_file, True
            else:
                # Return file anyway if upload fails (better than nothing)
                logger.warning("Fallback upload failed, but returning downloaded file.")
                return fallback_file, True

        # 4. All failed
        logger.error("❌ All download methods failed.")
        return None, False

    # ---------- UTILITY METHODS (unchanged) ----------
    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        return []

    async def _get_video_details(self, link: str, limit: int = 1) -> Union[dict, None]:
        try:
            results = VideosSearch(link, limit=limit)
            search_results = (await results.next()).get("result", [])
            for result in search_results:
                return result
            search = CustomSearch(query=link, searchPreferences="EgIYAw==", limit=1)
            for res in (await search.next()).get("result", []):
                return res
            return None
        except Exception:
            return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await self._get_video_details(link)
        if not result:
            raise ValueError("No suitable video found")
        dur = result.get("duration", "0:00")
        if "live" in str(dur).lower():
            seconds = 0
        else:
            try:
                seconds = int(time_to_seconds(dur))
            except:
                seconds = 0
        thumb = result["thumbnails"][0]["url"].split("?")[0] if result.get("thumbnails") else ""
        return result["title"], result["duration"], seconds, thumb, result["id"]

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await self._get_video_details(link)
        return result["title"] if result else None

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await self._get_video_details(link)
        return result["duration"] if result else None

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await self._get_video_details(link)
        if result and result.get("thumbnails"):
            return result["thumbnails"][0]["url"].split("?")[0]
        return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await self._get_video_details(link)
        if not result:
            raise ValueError("No suitable video found")
        thumb = result["thumbnails"][0]["url"].split("?")[0] if result.get("thumbnails") else ""
        return {
            "title": result["title"],
            "link": result["link"],
            "vidid": result["id"],
            "duration_min": result["duration"],
            "thumb": thumb
        }, result["id"]

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        return [], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        search = VideosSearch(link, limit=10)
        results = (await search.next()).get("result", [])
        if not results:
            raise ValueError("No videos found")
        selected = results[query_type] if query_type < len(results) else results[0]
        thumb = selected["thumbnails"][0]["url"].split("?")[0] if selected.get("thumbnails") else ""
        return selected["title"], selected["duration"], thumb, selected["id"]

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None
