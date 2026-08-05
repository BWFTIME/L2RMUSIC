import asyncio
import os
import re
from typing import Union, Optional, Tuple
import yt_dlp
import aiohttp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from py_yt import VideosSearch, Playlist
from motor.motor_asyncio import AsyncIOMotorClient

from L2RMUSIC import LOGGER, app
from L2RMUSIC.utils.formatters import time_to_seconds

# --- CONFIG (Load from environment, with new channel ID as default) ---
PLAYLIST_ID = int(os.getenv("PLAYLIST_ID", "-1004441504296"))  # ✅ नई ID
MONGO_DB_URI = os.getenv("MONGO_DB_URI", "mongodb+srv://BWFMUSIC:BWFMUSIC@cluster0.xwnup2l.mongodb.net/?retryWrites=true&w=majority")
SHRUTI_API_URL = os.getenv("SHRUTI_API_URL", "https://api.shrutibots.site")
SHRUTI_API_KEY = os.getenv("SHRUTI_API_KEY", "ShrutiBotsvfxRF6Qt1ejYXnovI3TG")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")

logger = LOGGER(__name__)

# MongoDB Connection (safe)
try:
    _mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI, serverSelectionTimeoutMS=5000)
    mongodb = _mongo_async_.L2RMUSIC
    trackdb = mongodb.track_cache
    logger.info("MongoDB connected successfully.")
except Exception as e:
    logger.error(f"MongoDB Connection Error: {e}")
    trackdb = None

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ==========================================
# STANDALONE FUNCTIONS (For song.py plugin)
# ==========================================
async def download_song(link: str) -> Optional[str]:
    """Download audio from YouTube using Shruti API."""
    video_id = extract_video_id(link)
    if not video_id:
        return None
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
        return file_path

    try:
        async with aiohttp.ClientSession() as session:
            params = {"url": video_id, "type": "audio", "api_key": SHRUTI_API_KEY}
            async with session.get(f"{SHRUTI_API_URL}/download", params=params, timeout=300) as resp:
                if resp.status == 200:
                    with open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)
                    if os.path.getsize(file_path) > 2048:
                        return file_path
                    else:
                        os.remove(file_path)
                else:
                    logger.error(f"Shruti API error: {resp.status}")
    except Exception as e:
        logger.error(f"Song Download Error: {e}")
    return None


async def download_video(link: str) -> Optional[str]:
    """Download video from YouTube using Shruti API."""
    video_id = extract_video_id(link)
    if not video_id:
        return None
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
        return file_path

    try:
        async with aiohttp.ClientSession() as session:
            params = {"url": video_id, "type": "video", "api_key": SHRUTI_API_KEY}
            async with session.get(f"{SHRUTI_API_URL}/download", params=params, timeout=600) as resp:
                if resp.status == 200:
                    with open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)
                    if os.path.getsize(file_path) > 2048:
                        return file_path
                    else:
                        os.remove(file_path)
                else:
                    logger.error(f"Shruti API error: {resp.status}")
    except Exception as e:
        logger.error(f"Video Download Error: {e}")
    return None


def extract_video_id(link: str) -> Optional[str]:
    """Extract video ID from various YouTube URL formats."""
    if "v=" in link:
        return link.split("v=")[-1].split("&")[0]
    elif "youtu.be/" in link:
        return link.split("/")[-1].split("?")[0]
    return None


# ==========================================
# MAIN YOUTUBE API CLASS
# ==========================================
class YouTubeAPI:
    """Handles YouTube metadata fetching, downloading, and caching."""

    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.valid_exts = ["m4a", "mp4", "mp3", "webm"]

    def _find_file(self, vid_id: str, is_video: bool = False) -> Optional[str]:
        """Search local directory for an existing file of the given video ID."""
        if not os.path.exists(DOWNLOAD_DIR):
            return None
        # Preferred extension based on type
        ext = "mp4" if is_video else "mp3"
        preferred_path = os.path.join(DOWNLOAD_DIR, f"{vid_id}.{ext}")
        if os.path.exists(preferred_path) and os.path.getsize(preferred_path) > 2048:
            return os.path.abspath(preferred_path)
        # Fallback: check all extensions
        for ext in self.valid_exts:
            filepath = os.path.join(DOWNLOAD_DIR, f"{vid_id}.{ext}")
            if os.path.exists(filepath):
                if os.path.getsize(filepath) > 2048:
                    return os.path.abspath(filepath)
                else:
                    try:
                        os.remove(filepath)
                    except:
                        pass
        return None

    async def _upload_to_cache(self, vid_id: str, file_path: str, title: str, is_video: bool):
        """Upload file to Telegram channel and store message ID in DB (with error handling)."""
        if trackdb is None or not os.path.exists(file_path):
            return
        try:
            db_id = f"{vid_id}_video" if is_video else vid_id
            # Check if already cached
            exists = await trackdb.find_one({"vid_id": db_id})
            if exists:
                return

            logger.info(f"📤 Uploading to Channel: {title}")
            mention = app.me.mention if app.me else "Bot"
            cap = f"**Song:** {title}\n**ID:** `{vid_id}`\n**Saved by:** {mention}"

            # Try to send media – catch any peer/permission errors
            try:
                if is_video:
                    msg = await app.send_video(PLAYLIST_ID, file_path, caption=cap, supports_streaming=True)
                else:
                    msg = await app.send_audio(PLAYLIST_ID, file_path, caption=cap, title=title)
            except Exception as send_err:
                logger.warning(f"Cannot send to channel (ID: {PLAYLIST_ID}): {send_err}")
                return  # Don't store in DB if upload fails

            if msg:
                await trackdb.update_one(
                    {"vid_id": db_id},
                    {
                        "$set": {
                            "message_id": msg.id,
                            "title": title,
                            "type": "video" if is_video else "audio"
                        }
                    },
                    upsert=True
                )
                logger.info(f"✅ Upload Complete (Msg ID: {msg.id})")
        except Exception as e:
            logger.error(f"Cache Upload Error: {e}")

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None
    ) -> Tuple[Optional[str], bool]:
        """
        Main download method. Returns (file_path, success).
        Tries local cache → DB cache → Shruti API → yt-dlp fallback.
        """
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        vid_id = extract_video_id(link)
        if not vid_id:
            logger.error("Invalid YouTube link")
            return None, False

        is_video = bool(video or songvideo)
        title = title or vid_id

        # 1. Local Cache
        local_path = self._find_file(vid_id, is_video)
        if local_path:
            logger.info(f"✅ Found local file: {local_path}")
            return local_path, True

        # 2. Database Cache (via Telegram) – with proper exception handling
        if trackdb is not None:
            try:
                db_id = f"{vid_id}_video" if is_video else vid_id
                doc = await asyncio.wait_for(trackdb.find_one({"vid_id": db_id}), timeout=5.0)
                if doc and "message_id" in doc:
                    try:
                        msg = await app.get_messages(PLAYLIST_ID, doc['message_id'])
                    except Exception as get_err:
                        # If we can't fetch from channel (peer invalid, not member, etc.)
                        logger.warning(f"Cache retrieval failed (channel {PLAYLIST_ID}): {get_err}")
                        msg = None
                    if msg and not msg.empty:
                        media = msg.video or msg.audio or msg.document or msg.voice
                        if media:
                            temp_path = os.path.join(DOWNLOAD_DIR, f"{vid_id}.{'mp4' if is_video else 'mp3'}")
                            file = await app.download_media(media.file_id, file_name=temp_path)
                            if file and os.path.getsize(file) > 2048:
                                logger.info(f"✅ Downloaded from Telegram cache: {file}")
                                return file, True
            except Exception as e:
                logger.error(f"DB Fetch Error: {e}")

        # 3. Shruti API
        ext = "mp4" if is_video else "mp3"
        type_str = "video" if is_video else "audio"
        file_path = os.path.join(DOWNLOAD_DIR, f"{vid_id}.{ext}")
        try:
            logger.info(f"🛡️ Using Shruti API for {vid_id}")
            async with aiohttp.ClientSession() as session:
                params = {"url": vid_id, "type": type_str, "api_key": SHRUTI_API_KEY}
                async with session.get(f"{SHRUTI_API_URL}/download", params=params, timeout=300) as resp:
                    if resp.status == 200:
                        with open(file_path, "wb") as f:
                            async for chunk in resp.content.iter_chunked(131072):
                                f.write(chunk)
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                            asyncio.create_task(self._upload_to_cache(vid_id, file_path, title, is_video))
                            logger.info(f"✅ Downloaded via Shruti API: {file_path}")
                            return file_path, True
                        else:
                            os.remove(file_path)
                            logger.warning("Downloaded file too small, removed.")
                    else:
                        logger.error(f"Shruti API returned {resp.status}")
        except Exception as e:
            logger.error(f"API Download Failed: {e}")

        # 4. Ultimate Fallback: yt-dlp
        try:
            logger.info(f"🔄 Using yt-dlp fallback for {vid_id}")
            opts = {
                'format': 'bestaudio/best' if not is_video else 'best',
                'outtmpl': os.path.join(DOWNLOAD_DIR, f"{vid_id}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
            }
            def _ytdl_download():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    return ydl.prepare_filename(info)

            loop = asyncio.get_event_loop()
            dl_path = await loop.run_in_executor(None, _ytdl_download)
            if dl_path and os.path.exists(dl_path) and os.path.getsize(dl_path) > 2048:
                logger.info(f"✅ Downloaded via yt-dlp: {dl_path}")
                return dl_path, True
        except Exception as e:
            logger.error(f"yt-dlp fallback failed: {e}")

        return None, False

    # --- Metadata Methods (with proper error handling) ---
    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Optional[str]:
        """Extract YouTube URL from a Telegram message."""
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

    async def details(self, link: str, videoid: Union[bool, str] = None):
        """Get title, duration, thumbnail, video ID."""
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                title = result["title"]
                duration_min = result["duration"]
                thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                vidid = result["id"]
                duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
                return title, duration_min, duration_sec, thumbnail, vidid
        except Exception as e:
            logger.error(f"details error: {e}")
        return "Unknown", "0:00", 0, "https://telegra.ph/file/default.jpg", ""

    async def title(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["title"]
        except Exception as e:
            logger.error(f"title error: {e}")
        return "Unknown"

    async def duration(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["duration"]
        except Exception as e:
            logger.error(f"duration error: {e}")
        return "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["thumbnails"][0]["url"].split("?")[0]
        except Exception as e:
            logger.error(f"thumbnail error: {e}")
        return "https://telegra.ph/file/default.jpg"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            plist = await Playlist.get(link)
            videos = plist.get("videos") or []
            ids = [data.get("id") for data in videos[:limit] if data.get("id")]
            return ids
        except Exception as e:
            logger.error(f"playlist error: {e}")
            return []

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                title = result["title"]
                duration_min = result["duration"]
                vidid = result["id"]
                yturl = result["link"]
                thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                return {
                    "title": title,
                    "link": yturl,
                    "vidid": vidid,
                    "duration_min": duration_min,
                    "thumb": thumbnail
                }, vidid
        except Exception as e:
            logger.error(f"track error: {e}")
            raise ValueError("Track not found")

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        ytdl_opts = {"quiet": True, "no_warnings": True}
        try:
            def _get_formats():
                with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                    formats_available = []
                    r = ydl.extract_info(link, download=False)
                    for f in r.get("formats", []):
                        if "dash" not in str(f.get("format", "")).lower():
                            formats_available.append({
                                "format": f.get("format"),
                                "filesize": f.get("filesize"),
                                "format_id": f.get("format_id"),
                                "ext": f.get("ext"),
                                "format_note": f.get("format_note"),
                                "yturl": link
                            })
                    return formats_available
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(None, _get_formats)
            return res, link
        except Exception as e:
            logger.error(f"formats error: {e}")
            return [], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            a = VideosSearch(link, limit=10)
            res = (await a.next()).get("result", [])
            result = res[query_type] if query_type < len(res) else res[0]
            return result["title"], result["duration"], result["thumbnails"][0]["url"].split("?")[0], result["id"]
        except Exception as e:
            logger.error(f"slider error: {e}")
            return "Unknown", "0:00", "https://telegra.ph/file/default.jpg", ""


# Global instance
YouTube = YouTubeAPI()
