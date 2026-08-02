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

# --- CONFIG VALUES ---
YT_API_KEY = "30DxNexGenBots0055e5"
YTPROXY = "https://tgapi.xbitcode.com"

# Aapki nayi channel ID set kar di gayi hai
PLAYLIST_ID = -1004493387604 

MONGO_DB_URI = "mongodb+srv://L2RKING:BWF_MUSIC1@l2rking.1ikcd.mongodb.net/?retryWrites=true&w=majority"
LIMIT_SECONDS = 900
DOWNLOAD_DIR = "downloads"

# --- NEW API CONFIG ---
API_URL = os.environ.get("SHRUTI_API_URL", "https://shrutibots.site")
API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotswUiyhdS8Fmjt8limDX69") 
SHRUTI_RELATED_URL = "https://shrutibots.site/related"
SHRUTI_RELATED_KEY = "ShrutiBotsV1npoyhq8PrrjlVADSPU"
INFLEX_RELATED_URL = "https://teaminflex.xyz/related"
INFLEX_RELATED_KEY = "INFLEX99600328D"

# --- FALLBACK API CONFIG ---
YOUR_API_URL = None
FALLBACK_API_URL = "https://shrutibots.site"

# --- DATABASE CONNECTION ---
_mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
mongodb = _mongo_async_.L2RMUSIC
trackdb = mongodb.track_cache

# --- HELPER FUNCTIONS ---
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

# --- DIRECT DOWNLOAD FUNCTIONS ---
async def download_song(link: str) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link.split("/")[-1]
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/download",
                params={"url": video_id, "type": "audio", "api_key": API_KEY},
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                if resp.status != 200:
                    return None
                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
        return None
    except Exception as e:
        logger.error(f"Download Song Error: {e}")
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass
        return None

async def download_video(link: str) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link.split("/")[-1]
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/download",
                params={"url": video_id, "type": "video", "api_key": API_KEY},
                timeout=aiohttp.ClientTimeout(total=600)
            ) as resp:
                if resp.status != 200:
                    return None
                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
        return None
    except Exception as e:
        logger.error(f"Download Video Error: {e}")
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass
        return None

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

    # --- UNIVERSAL CACHING (Name & MP3 Fix) ---
    async def _upload_to_cache(self, vid_id, file_path, title, is_video):
        try:
            if not os.path.exists(file_path): 
                return
            
            db_id = f"{vid_id}_video" if is_video else vid_id
            exists = await trackdb.find_one({"vid_id": db_id})
            if exists: 
                return

            try:
                await app.get_chat(PLAYLIST_ID)
            except Exception:
                pass

            bot_name = app.me.mention if (app and app.me) else "Bot"
            
            # Yahan Caption proper Name aur ID ke sath jayega
            cap = f"**Song:** {title}\n**ID:** `{vid_id}`\n**Saved by:** {bot_name}"
            
            # File ka proper naam set karna
            clean_title = "".join(x for x in title if x.isalnum() or x in " -_")
            
            msg = None
            try:
                if is_video:
                    msg = await app.send_video(
                        PLAYLIST_ID, 
                        file_path, 
                        caption=cap, 
                        supports_streaming=True,
                        file_name=f"{clean_title}.mp4"
                    )
                else:
                    msg = await app.send_audio(
                        PLAYLIST_ID, 
                        file_path, 
                        caption=cap, 
                        title=title,
                        performer=bot_name,
                        file_name=f"{clean_title}.mp3"
                    )
            except Exception as e:
                logger.error(f"Upload skipped due to Error: {e}")
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
        except Exception as e:
            logger.error(f"Cache Error: {e}")

    async def get_cached_file(self, vid_id: str, is_video: bool = False):
        db_id = f"{vid_id}_video" if is_video else vid_id
        local_path = self._find_file(vid_id)
        if local_path: return local_path

        doc = await trackdb.find_one({"vid_id": db_id})
        
        if doc and "message_id" in doc:
            message_id = doc['message_id']
            ext = "mp4" if is_video else "mp3"
            temp_path = os.path.join(DOWNLOAD_DIR, f"{vid_id}.{ext}")
            
            try:
                cached_msg = await app.get_messages(PLAYLIST_ID, message_id)
                
                if not cached_msg or cached_msg.empty:
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
        
        return None

    # --- GET RELATED ---
    async def get_related(self, videoid: str, limit: int = 5) -> list:
        related_tracks = []
        try:
            async with aiohttp.ClientSession() as session:
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

        # 🔥 STRONG TITLE FETCHER: Ab asli gaane ka naam hi aayega
        if not title or title == vid_id or "http" in title:
            try:
                ydl_opts = {"quiet": True, "extract_flat": True, "skip_download": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                    if info and "title" in info:
                        title = info["title"]
            except Exception:
                pass
            
            # Agar yt_dlp fail ho jaye, to Pyrogram YoutubeSearch use karo
            if not title or title == vid_id or "http" in title:
                try:
                    fetched_title = await self.title(link)
                    if fetched_title:
                        title = fetched_title
                except Exception:
                    pass
            
            if not title:
                title = vid_id

        # 1. CHECK DB CACHE
        cached_path = await self.get_cached_file(vid_id, is_video=is_video_request)
        if cached_path: 
            return cached_path, True

        # 2. DOWNLOAD USING NEW API
        if is_video_request:
            downloaded_file = await download_video(link)
        else:
            downloaded_file = await download_song(link)

        # 3. CACHE IT & RETURN
        if downloaded_file:
            await self._upload_to_cache(vid_id, downloaded_file, title, is_video_request)
            return downloaded_file, True
        
        return None, False

    # --- UTILS ---
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
    
