import asyncio
import os
import re
from typing import Union
import aiohttp
import aiofiles
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch, CustomSearch
from py_yt import Playlist
from L2RMUSIC import LOGGER, app 
from L2RMUSIC.utils.formatters import time_to_seconds
from motor.motor_asyncio import AsyncIOMotorClient

logger = LOGGER(__name__)

# --- CONFIG (Use env variables for safety) ---
YT_API_KEY = os.environ.get("YT_API_KEY", "30DxNexGenBots0055e5")
YTPROXY = os.environ.get("YTPROXY", "https://tgapi.xbitcode.com")
PLAYLIST_ID = os.environ.get("CACHE_CHANNEL_ID", -1003616869403)  # yeh value update karo agar channel change ho
MONGO_DB_URI = os.environ.get("MONGO_DB_URI", "mongodb+srv://L2RKING:BWF_MUSIC1@l2rking.1ikcd.mongodb.net/?retryWrites=true&w=majority")
LIMIT_SECONDS = int(os.environ.get("LIMIT_SECONDS", 900))
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads")

# --- API CONFIG ---
API_URL = os.environ.get("SHRUTI_API_URL", "https://shrutibots.site")
API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotswUiyhdS8Fmjt8limDX69")
SHRUTI_RELATED_URL = os.environ.get("SHRUTI_RELATED_URL", "https://shrutibots.site/related")
SHRUTI_RELATED_KEY = os.environ.get("SHRUTI_RELATED_KEY", "ShrutiBotsV1npoyhq8PrrjlVADSPU")
INFLEX_RELATED_URL = os.environ.get("INFLEX_RELATED_URL", "https://teaminflex.xyz/related")
INFLEX_RELATED_KEY = os.environ.get("INFLEX_RELATED_KEY", "INFLEX99600328D")

# --- FALLBACK API (from pastebin) ---
FALLBACK_API_URL = "https://shrutibots.site"
YOUR_API_URL = None

# --- DATABASE ---
_mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
mongodb = _mongo_async_.L2RMUSIC
trackdb = mongodb.track_cache

# --- HELPER ---
def get_time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))

async def load_api_url():
    global YOUR_API_URL
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://pastebin.com/raw/rLsBhAQa", timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    YOUR_API_URL = (await response.text()).strip()
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

# --- YT-DLP FALLBACK DOWNLOAD FUNCTIONS ---
async def _download_with_ytdlp(link: str, is_video: bool = False) -> Union[str, None]:
    """Direct download using yt-dlp as fallback."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link.split("/")[-1]
    if not video_id or len(video_id) < 3:
        return None

    ext = "mp4" if is_video else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
        return file_path

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": file_path,
        "format": "bestaudio/best" if not is_video else "bestvideo+bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }] if not is_video else [],
        "noplaylist": True,
    }
    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await loop.run_in_executor(None, lambda: ydl.download([link]))
        if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
            return file_path
        return None
    except Exception as e:
        logger.error(f"yt-dlp download error: {e}")
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass
        return None

async def download_song(link: str) -> str:
    """Try API first, then fallback to yt-dlp."""
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link.split("/")[-1]
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
        return file_path

    # Try API
    try:
        async with aiohttp.ClientSession() as session:
            # Use YOUR_API_URL if available, else API_URL
            base_url = YOUR_API_URL if YOUR_API_URL else API_URL
            async with session.get(
                f"{base_url}/download",
                params={"url": video_id, "type": "audio", "api_key": API_KEY},
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                if resp.status == 200:
                    with open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                        return file_path
    except Exception as e:
        logger.warning(f"API download failed: {e}, trying yt-dlp...")

    # Fallback to yt-dlp
    return await _download_with_ytdlp(link, is_video=False)

async def download_video(link: str) -> str:
    """Try API first, then fallback to yt-dlp."""
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link.split("/")[-1]
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
        return file_path

    # Try API
    try:
        async with aiohttp.ClientSession() as session:
            base_url = YOUR_API_URL if YOUR_API_URL else API_URL
            async with session.get(
                f"{base_url}/download",
                params={"url": video_id, "type": "video", "api_key": API_KEY},
                timeout=aiohttp.ClientTimeout(total=600)
            ) as resp:
                if resp.status == 200:
                    with open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(131072):
                            f.write(chunk)
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                        return file_path
    except Exception as e:
        logger.warning(f"API download failed: {e}, trying yt-dlp...")

    # Fallback to yt-dlp
    return await _download_with_ytdlp(link, is_video=True)

# --- YOUTUBEAPI CLASS (Fixed) ---
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    def _find_file(self, vid_id):
        if not os.path.exists(DOWNLOAD_DIR): return None
        for ext in ["m4a", "mp4", "mp3", "webm"]:
            filepath = f"{DOWNLOAD_DIR}/{vid_id}.{ext}"
            if os.path.exists(filepath):
                if os.path.getsize(filepath) > 2048:
                    return os.path.abspath(filepath)
                else:
                    try: os.remove(filepath)
                    except: pass
        return None

    # --- CACHING (with error handling for invalid playlist) ---
    async def _upload_to_cache(self, vid_id, file_path, title, is_video):
        if not PLAYLIST_ID:
            return
        try:
            if not os.path.exists(file_path): return
            
            db_id = f"{vid_id}_video" if is_video else vid_id
            exists = await trackdb.find_one({"vid_id": db_id})
            if exists: return

            logger.info(f"📤 Uploading to Channel: {title}")
            cap = f"**Song:** {title}\n**ID:** `{vid_id}`\n**Saved by:** {app.me.mention}"
            
            msg = None
            try:
                if is_video:
                    msg = await app.send_video(PLAYLIST_ID, file_path, caption=cap, supports_streaming=True)
                else:
                    msg = await app.send_audio(PLAYLIST_ID, file_path, caption=cap, title=title)
            except Exception as e:
                logger.error(f"Failed to upload to cache channel (check if bot is member): {e}")
                return

            if msg:
                await trackdb.update_one(
                    {"vid_id": db_id},
                    {"$set": {
                        "message_id": msg.id, 
                        "title": title,
                        "type": "video" if is_video else "audio"
                    }},
                    upsert=True
                )
                logger.info(f"✅ Upload Complete (Msg ID: {msg.id}): {title}")
        except Exception as e:
            logger.error(f"Upload Error: {e}")

    async def get_cached_file(self, vid_id: str, is_video: bool = False):
        if not PLAYLIST_ID:
            return None

        db_id = f"{vid_id}_video" if is_video else vid_id
        local_path = self._find_file(vid_id)
        if local_path: return local_path

        doc = await trackdb.find_one({"vid_id": db_id})
        if doc and "message_id" in doc:
            message_id = doc['message_id']
            ext = "mp4" if is_video else "mp3"
            temp_path = os.path.join(DOWNLOAD_DIR, f"{vid_id}.{ext}")
            
            try:
                logger.info(f"🔄 Fetching from Channel (Msg ID: {message_id})")
                cached_msg = await app.get_messages(PLAYLIST_ID, message_id)
                
                if not cached_msg or cached_msg.empty:
                    logger.warning("Message not found/deleted in channel, cleaning DB.")
                    await trackdb.delete_one({"vid_id": db_id})
                    return None

                media_file = None
                if cached_msg.video: media_file = cached_msg.video.file_id
                elif cached_msg.audio: media_file = cached_msg.audio.file_id
                elif cached_msg.document: media_file = cached_msg.document.file_id
                elif cached_msg.voice: media_file = cached_msg.voice.file_id

                if media_file:
                    file = await app.download_media(media_file, file_name=temp_path)
                    if file and os.path.exists(file) and os.path.getsize(file) > 2048:
                        return file
                
                if os.path.exists(temp_path): os.remove(temp_path)
            except Exception as e:
                logger.error(f"Cache Retrieval Failed: {e}")
                if os.path.exists(temp_path): os.remove(temp_path)
                # If peer invalid, maybe delete DB entry to avoid repeated errors
                if "Peer id invalid" in str(e) or "ID not found" in str(e):
                    await trackdb.delete_one({"vid_id": db_id})
        return None

    # --- GET RELATED ---
    async def get_related(self, videoid: str, limit: int = 5) -> list:
        related_tracks = []
        try:
            async with aiohttp.ClientSession() as session:
                # 1. Try Shruti API
                try:
                    async with session.get(
                        SHRUTI_RELATED_URL,
                        params={"id": videoid, "apikey": SHRUTI_RELATED_KEY},
                        timeout=5
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if isinstance(data, list): related_tracks = data
                            elif isinstance(data, dict): related_tracks = data.get("results") or data.get("data") or data.get("items") or []
                except Exception:
                    pass

                # 2. Fallback to Inflex
                if not related_tracks:
                    try:
                        async with session.get(
                            INFLEX_RELATED_URL,
                            params={"id": videoid, "apikey": INFLEX_RELATED_KEY},
                            timeout=5
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if isinstance(data, list): related_tracks = data
                                elif isinstance(data, dict): related_tracks = data.get("results") or data.get("data") or data.get("items") or []
                    except Exception:
                        pass
        except Exception:
            pass
        return related_tracks

    # --- MAIN DOWNLOAD (with fallback) ---
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
        if videoid:
            vid_id = link
            link = self.base + link
        else:
            if "v=" in link: vid_id = link.split('v=')[-1].split('&')[0]
            else: vid_id = link.split('/')[-1]

        is_video_request = bool(video or songvideo)

        # 1. Check Cache
        cached_path = await self.get_cached_file(vid_id, is_video=is_video_request)
        if cached_path: 
            return cached_path, True

        # 2. Download (API + yt-dlp fallback)
        if is_video_request:
            downloaded_file = await download_video(link)
        else:
            downloaded_file = await download_song(link)

        if downloaded_file:
            # Upload to cache in background
            asyncio.create_task(self._upload_to_cache(vid_id, downloaded_file, title or vid_id, is_video_request))
            return downloaded_file, True

        logger.error("❌ All Download APIs Failed.")
        return None, False

    # --- ALL OTHER METHODS (unchanged, kept as is) ---
    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))
    
    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message: messages.append(message_1.reply_to_message)
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

    async def _get_video_details(self, link: str, limit: int = 1) -> Union[dict, None]:
        try:
            results = VideosSearch(link, limit=limit)
            search_results = (await results.next()).get("result", [])
            for result in search_results: return result
            search = CustomSearch(query=link, searchPreferences="EgIYAw==", limit=1)
            for res in (await search.next()).get("result", []): return res
            return None
        except: return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        result = await self._get_video_details(link)
        if not result: raise ValueError("No suitable video found")
        dur = result.get("duration", "0:00")
        if "live" in str(dur).lower(): seconds = 0
        else:
            try: seconds = int(get_time_to_seconds(dur))
            except: seconds = 0
        return result["title"], result["duration"], seconds, result["thumbnails"][0]["url"].split("?")[0], result["id"]
    
    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        result = await self._get_video_details(link)
        return result["title"] if result else None

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        result = await self._get_video_details(link)
        return result["duration"] if result else None

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        result = await self._get_video_details(link)
        return result["thumbnails"][0]["url"].split("?")[0] if result else None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        result = await self._get_video_details(link)
        if not result: raise ValueError("No suitable video found")
        return {"title": result["title"], "link": result["link"], "vidid": result["id"], "duration_min": result["duration"], "thumb": result["thumbnails"][0]["url"].split("?")[0]}, result["id"]

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            plist = await Playlist.get(link)
        except Exception:
            return []
        videos = plist.get("videos") or []
        ids = []
        for data in videos[:limit]:
            if not data:
                continue
            vid = data.get("id")
            if not vid:
                continue
            ids.append(vid)
        return ids

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        ytdl_opts = {"quiet": True}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for format in r["formats"]:
                try:
                    if "dash" not in str(format["format"]).lower():
                        formats_available.append(
                            {
                                "format": format["format"],
                                "filesize": format.get("filesize"),
                                "format_id": format["format_id"],
                                "ext": format["ext"],
                                "format_note": format["format_note"],
                                "yturl": link,
                            }
                        )
                except Exception:
                    continue
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        search = VideosSearch(link, limit=10)
        results = (await search.next()).get("result", [])
        if not results: raise ValueError("No videos found")
        selected = results[query_type] if query_type < len(results) else results[0]
        return selected["title"], selected["duration"], selected["thumbnails"][0]["url"].split("?")[0], selected["id"]

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
            return 0, "Video download failed"
        except Exception as e:
            return 0, f"Video download error: {e}"
