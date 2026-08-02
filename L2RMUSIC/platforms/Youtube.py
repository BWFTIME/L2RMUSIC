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

# --- CONFIG VALUES (unchanged) ---
YT_API_KEY = "30DxNexGenBots0055e5"
YTPROXY = "https://tgapi.xbitcode.com"
PLAYLIST_ID = -1003616869403
MONGO_DB_URI = "mongodb+srv://L2RKING:BWF_MUSIC1@l2rking.1ikcd.mongodb.net/?retryWrites=true&w=majority"
LIMIT_SECONDS = 900
DOWNLOAD_DIR = "downloads"

API_URL = os.environ.get("SHRUTI_API_URL", "https://shrutibots.site")
API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotswUiyhdS8Fmjt8limDX69") 
SHRUTI_RELATED_URL = "https://shrutibots.site/related"
SHRUTI_RELATED_KEY = "ShrutiBotsV1npoyhq8PrrjlVADSPU"
INFLEX_RELATED_URL = "https://teaminflex.xyz/related"
INFLEX_RELATED_KEY = "INFLEX99600328D"

YOUR_API_URL = None
FALLBACK_API_URL = "https://shrutibots.site"

_mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
mongodb = _mongo_async_.L2RMUSIC
trackdb = mongodb.track_cache

# --- Helper functions (unchanged) ---
def get_time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))

async def load_api_url():
    global YOUR_API_URL
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://pastebin.com/raw/rLsBhAQa", timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    content = await response.text()
                    YOUR_API_URL = content.strip()
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

# --- Direct download functions (unchanged) ---
async def download_song(link: str) -> str:
    # ... same as before
    pass

async def download_video(link: str) -> str:
    # ... same as before
    pass


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        
        # Create index on 'title' for fast searches
        asyncio.create_task(self._ensure_indexes())

    async def _ensure_indexes(self):
        """Create database indexes if they don't exist."""
        try:
            await trackdb.create_index("title")
            logger.info("✅ Created index on 'title' for track_cache")
        except Exception as e:
            logger.warning(f"Could not create index: {e}")

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

    async def _download_from_message(self, message_id: int, vid_id: str, is_video: bool):
        """Download media from a cached Telegram message."""
        ext = "mp4" if is_video else "mp3"
        temp_path = os.path.join(DOWNLOAD_DIR, f"{vid_id}.{ext}")
        try:
            cached_msg = await app.get_messages(PLAYLIST_ID, message_id)
            if not cached_msg or cached_msg.empty:
                logger.warning(f"Message {message_id} not found, cleaning DB.")
                await trackdb.delete_one({"message_id": message_id})
                return None

            media_file = None
            if cached_msg.video:
                media_file = cached_msg.video.file_id
            elif cached_msg.audio:
                media_file = cached_msg.audio.file_id
            elif cached_msg.document:
                media_file = cached_msg.document.file_id
            elif cached_msg.voice:
                media_file = cached_msg.voice.file_id

            if media_file:
                file = await app.download_media(media_file, file_name=temp_path)
                if file and os.path.exists(file) and os.path.getsize(file) > 2048:
                    return file
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            logger.error(f"Download from message {message_id} failed: {e}")
        return None

    async def get_cached_file(self, vid_id: str = None, is_video: bool = False, title: str = None):
        """
        Retrieve a cached file either by video ID or by title (fallback).
        Returns file path if found, else None.
        """
        # 1. Try by video ID if provided
        if vid_id:
            db_id = f"{vid_id}_video" if is_video else vid_id
            local_path = self._find_file(vid_id)
            if local_path:
                return local_path

            doc = await trackdb.find_one({"vid_id": db_id})
            if doc and "message_id" in doc:
                file_path = await self._download_from_message(doc["message_id"], vid_id, is_video)
                if file_path:
                    return file_path
                else:
                    # if download failed, remove this DB entry
                    await trackdb.delete_one({"vid_id": db_id})

        # 2. Fallback: search by title (case‑insensitive exact match)
        if title:
            # Build query: match title case-insensitively and type
            query = {
                "title": {"$regex": f"^{title}$", "$options": "i"},
                "type": "video" if is_video else "audio"
            }
            doc = await trackdb.find_one(query)
            if doc and "message_id" in doc:
                # extract actual vid_id from stored db_id
                stored_id = doc["vid_id"]
                if stored_id.endswith("_video"):
                    actual_vid_id = stored_id[:-6]
                else:
                    actual_vid_id = stored_id
                file_path = await self._download_from_message(doc["message_id"], actual_vid_id, is_video)
                if file_path:
                    return file_path
                else:
                    await trackdb.delete_one({"_id": doc["_id"]})
        return None

    async def _upload_to_cache(self, vid_id, file_path, title, is_video):
        # ... unchanged ...
        try:
            if not os.path.exists(file_path): return
            
            db_id = f"{vid_id}_video" if is_video else vid_id
            exists = await trackdb.find_one({"vid_id": db_id})
            if exists: return

            logger.info(f"📤 Uploading to Channel: {title}")
            cap = f"**Song:** {title}\n**ID:** `{vid_id}`\n**Saved by:** {app.me.mention}"
            
            msg = None
            if is_video:
                msg = await app.send_video(PLAYLIST_ID, file_path, caption=cap, supports_streaming=True)
            else:
                msg = await app.send_audio(PLAYLIST_ID, file_path, caption=cap, title=title)

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
    ) -> str:
        if videoid:
            vid_id = link
            link = self.base + link
        else:
            if "v=" in link: vid_id = link.split('v=')[-1].split('&')[0]
            else: vid_id = link.split('/')[-1]

        is_video_request = bool(video or songvideo)

        # 1. Check DB cache – first by vid_id, then by title if provided
        cached_path = await self.get_cached_file(vid_id, is_video=is_video_request, title=title)
        if cached_path: 
            return cached_path, True

        # 2. Download using Shruti / fallback APIs
        if is_video_request:
            downloaded_file = await download_video(link)
        else:
            downloaded_file = await download_song(link)

        # 3. If download succeeded, cache and return
        if downloaded_file:
            # Upload to TG channel in background
            asyncio.create_task(self._upload_to_cache(vid_id, downloaded_file, title or vid_id, is_video_request))
            return downloaded_file, True
        
        logger.error("❌ All Download APIs Failed.")
        return None, False

    # --- All other methods (exists, url, details, track, playlist, etc.) remain unchanged ---
    # They are omitted here for brevity, but you must keep them as they are.
    # ...                        async with session.get(
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

    # --- MAIN DOWNLOAD FUNCTION COMBINED ---
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
    ) -> str:
        if videoid:
            vid_id = link
            link = self.base + link
        else:
            if "v=" in link: vid_id = link.split('v=')[-1].split('&')[0]
            else: vid_id = link.split('/')[-1]

        is_video_request = bool(video or songvideo)

        # 1. CHECK DB CACHE (Fastest)
        cached_path = await self.get_cached_file(vid_id, is_video=is_video_request)
        if cached_path: 
            return cached_path, True

        # 2. DOWNLOAD USING NEW API (Shruti)
        if is_video_request:
            downloaded_file = await download_video(link)
        else:
            downloaded_file = await download_song(link)

        # 3. IF DOWNLOAD SUCCESS, CACHE IT & RETURN
        if downloaded_file:
            # Upload to TG channel in background
            asyncio.create_task(self._upload_to_cache(vid_id, downloaded_file, title or vid_id, is_video_request))
            return downloaded_file, True
        
        logger.error("❌ All Download APIs Failed.")
        return None, False


    # --- UTILS (Kept from both files to ensure compatibility) ---
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
                        
