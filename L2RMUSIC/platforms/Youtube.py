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
PLAYLIST_ID = -1003616869403  # Ensure this is a valid channel/supergroup ID
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

# --- LOAD FALLBACK API URL ---
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

# Start loading
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

    # ---------- LOCAL FILE HELPERS ----------
    def _find_file(self, vid_id: str) -> Optional[str]:
        """Check if a valid local file exists for the video ID."""
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
        """Download a media file using its file_id directly."""
        try:
            file = await app.download_media(file_id, file_name=output_path)
            if file and os.path.exists(file) and os.path.getsize(file) > 2048:
                return file
        except Exception as e:
            logger.error(f"Download from file_id failed: {e}")
        return None

    # ---------- CACHE: STORE FILE_ID ----------
    async def _upload_to_cache(self, vid_id: str, file_path: str, title: str, is_video: bool):
        """Upload file to channel and store its file_id in DB."""
        try:
            if not os.path.exists(file_path):
                return

            db_id = f"{vid_id}_video" if is_video else vid_id

            # Check if already cached
            existing = await trackdb.find_one({"vid_id": db_id})
            if existing:
                return

            logger.info(f"📤 Uploading to Channel: {title}")
            cap = f"**Song:** {title}\n**ID:** `{vid_id}`\n**Saved by:** {app.me.mention}"

            if is_video:
                msg = await app.send_video(PLAYLIST_ID, file_path, caption=cap, supports_streaming=True)
            else:
                msg = await app.send_audio(PLAYLIST_ID, file_path, caption=cap, title=title)

            if msg:
                # Extract the actual file_id (video or audio)
                file_id = None
                if is_video and msg.video:
                    file_id = msg.video.file_id
                elif not is_video and msg.audio:
                    file_id = msg.audio.file_id
                elif msg.document:
                    file_id = msg.document.file_id

                if file_id:
                    # Store file_id instead of message_id
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
                    logger.info(f"✅ Cached {title} with file_id: {file_id[:20]}...")
                else:
                    logger.warning("Upload successful but no file_id found!")
        except Exception as e:
            logger.error(f"Upload to cache failed: {e}")

    # ---------- RETRIEVE CACHED FILE ----------
    async def get_cached_file(self, vid_id: str, is_video: bool = False) -> Optional[str]:
        """
        Retrieve cached file:
        1. Check local storage.
        2. If not local, check DB for file_id and download.
        """
        db_id = f"{vid_id}_video" if is_video else vid_id

        # 1. Check local
        local_path = self._find_file(vid_id)
        if local_path:
            return local_path

        # 2. Query DB for file_id
        try:
            doc = await trackdb.find_one({"vid_id": db_id})
            if doc and "file_id" in doc:
                file_id = doc["file_id"]
                output_path = os.path.join("downloads", f"{vid_id}.mp4")
                os.makedirs("downloads", exist_ok=True)

                # Download using the file_id directly (no get_messages needed)
                downloaded = await self._download_from_file_id(file_id, output_path)
                if downloaded:
                    return downloaded
                else:
                    # File ID might be invalid; remove from DB
                    await trackdb.delete_one({"vid_id": db_id})
                    logger.warning(f"Removed invalid cached entry for {vid_id}")
        except Exception as e:
            logger.error(f"Cache retrieval DB error: {e}")

        return None

    # ---------- API CALLS ----------
    async def get_api_url(self, vid_id: str, is_video: bool) -> Optional[str]:
        """Get direct download URL from primary API."""
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
        """Download using fallback API (streaming)."""
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

    # ---------- BACKGROUND CACHING ----------
    async def _background_process(self, vid_id: str, link: str, title: str, is_video: bool, duration_sec: int = 0):
        if duration_sec > LIMIT_SECONDS:
            return

        if self._find_file(vid_id):
            return

        os.makedirs("downloads", exist_ok=True)
        filepath = os.path.join("downloads", f"{vid_id}.mp4")

        # Try primary API for direct download
        try:
            direct_url = await self.get_api_url(vid_id, is_video)
            if direct_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(direct_url) as resp:
                        if resp.status == 200:
                            async with aiofiles.open(filepath, "wb") as f:
                                async for chunk in resp.content.iter_chunked(1048576):
                                    await f.write(chunk)
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 2048:
                                await self._upload_to_cache(vid_id, filepath, title, is_video)
                                return
        except Exception as e:
            logger.warning(f"Background primary download failed: {e}")

        # If primary fails, fallback download (will also cache)
        try:
            fallback_file = await self._external_api_download(vid_id, is_video)
            if fallback_file:
                await self._upload_to_cache(vid_id, fallback_file, title, is_video)
        except Exception as e:
            logger.warning(f"Background fallback download failed: {e}")

    # ---------- MAIN DOWNLOAD FUNCTION ----------
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
        Returns: (file_path_or_url, is_cached_or_direct)
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

        # 1. Check cache (local or file_id)
        cached_path = await self.get_cached_file(vid_id, is_video_request)
        if cached_path:
            return cached_path, True

        # 2. Try primary API streaming URL (without caching)
        try:
            api_url = await self.get_api_url(vid_id, is_video_request)
            if api_url:
                logger.info(f"🚀 Streaming from primary API: {title}")
                # Fire background download for future caching
                asyncio.create_task(self._background_process(vid_id, link, title, is_video_request))
                return api_url, True
        except Exception as e:
            logger.error(f"Primary API streaming failed: {e}")

        # 3. Fallback: download via fallback API (may take time)
        logger.warning(f"⚠️ Using fallback API for {vid_id}")
        fallback_file = await self._external_api_download(vid_id, is_video_request)
        if fallback_file:
            # Upload to cache for future
            await self._upload_to_cache(vid_id, fallback_file, title, is_video_request)
            return fallback_file, True

        # 4. No success
        logger.error("❌ All download methods failed.")
        return None, False

    # ---------- UTILITY METHODS (unchanged, with minor fixes) ----------
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
