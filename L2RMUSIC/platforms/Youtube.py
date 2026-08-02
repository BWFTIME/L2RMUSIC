import asyncio
import os
import re
import subprocess
import sys
from typing import Union, Optional
import aiohttp
import aiofiles
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from pyrogram.errors import PeerIdInvalid, ChannelInvalid, ChatWriteForbidden, ChatAdminRequired
from youtubesearchpython.__future__ import VideosSearch, CustomSearch
from L2RMUSIC import LOGGER, app
from L2RMUSIC.utils.formatters import time_to_seconds
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIG ---
YT_API_KEY = "ShrutiBotsOXrRk6qV3cgPptroKV1y"
YTPROXY = "https://tgapi.xbitcode.com"
PLAYLIST_ID = -1003616869403   # Ensure bot is admin here
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


# --- FIX: warm up the peer cache for the cache/upload channel ---
# Pyrogram raises "Peer id invalid" when it is asked to send to a chat ID
# it has never resolved in the current session (fresh session, bot just
# restarted, etc). Calling get_chat() once on startup forces pyrogram to
# resolve and cache that peer so later send_video/send_audio calls work.
async def resolve_playlist_peer():
    try:
        chat = await app.get_chat(PLAYLIST_ID)
        logger.info(f"✅ Resolved cache channel peer: {chat.title} ({PLAYLIST_ID})")
    except (PeerIdInvalid, ChannelInvalid):
        logger.error(
            f"❌ Could not resolve cache channel {PLAYLIST_ID}. "
            "Make sure the bot account is a member/admin of that channel "
            "and that the ID is correct (channel IDs must start with -100)."
        )
    except ChatAdminRequired:
        logger.error(f"❌ Bot is in {PLAYLIST_ID} but is not an admin there.")
    except Exception as e:
        logger.warning(f"Could not warm up cache channel peer: {e}")


async def _startup():
    await load_api_url()
    await resolve_playlist_peer()


try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(_startup())
    else:
        loop.run_until_complete(_startup())
except RuntimeError:
    pass

# --- CHECK YT-DLP ---
YTDLP_AVAILABLE = False
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
    logger.info("yt-dlp is available as a fallback.")
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
        import yt_dlp
        YTDLP_AVAILABLE = True
        logger.info("yt-dlp installed successfully as fallback.")
    except Exception as e:
        logger.warning(f"yt-dlp not available: {e}. Install manually with 'pip install yt-dlp'.")


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        self.upload_retries = 3
        self.download_timeout = 600  # seconds

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
                except Exception:
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
        if not os.path.exists(file_path):
            logger.error(f"File not found for upload: {file_path}")
            return False

        db_id = f"{vid_id}_video" if is_video else vid_id

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

            # FIX: catch the specific pyrogram "peer invalid" family of errors
            # and try to re-resolve the peer once before the next retry,
            # instead of silently burning all retries on a dead peer cache.
            except (PeerIdInvalid, ChannelInvalid) as e:
                logger.error(f"Peer invalid while uploading (attempt {attempt}): {e}")
                await resolve_playlist_peer()
            except ChatWriteForbidden:
                logger.error(f"Bot cannot write to cache channel {PLAYLIST_ID} (not admin / banned).")
                break
            except Exception as e:
                logger.error(f"Upload attempt {attempt} failed: {e}")

            if attempt < self.upload_retries:
                await asyncio.sleep(2)
            else:
                logger.error(f"All upload attempts failed for {title}")

        return False

    # ---------- RETRIEVE CACHED FILE ----------
    async def get_cached_file(self, vid_id: str, is_video: bool = False) -> Optional[str]:
        db_id = f"{vid_id}_video" if is_video else vid_id

        local_path = self._find_file(vid_id)
        if local_path:
            return local_path

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
                    await trackdb.delete_one({"vid_id": db_id})
                    logger.warning(f"Removed invalid cached entry for {vid_id}")
        except Exception as e:
            logger.error(f"Cache retrieval DB error: {e}")

        return None

    # ---------- PRIMARY API ----------
    async def get_api_url(self, vid_id: str, is_video: bool) -> Optional[str]:
        for attempt in range(1, 3):  # 2 retries
            try:
                if not YT_API_KEY or not YTPROXY:
                    return None
                headers = {
                    "x-api-key": YT_API_KEY,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                async with aiohttp.ClientSession() as session:
                    url = f"{YTPROXY}/info/{vid_id}"
                    async with session.get(url, headers=headers, timeout=10) as resp:
                        if resp.status != 200:
                            logger.warning(f"Primary API returned status {resp.status} (attempt {attempt})")
                            continue
                        data = await resp.json()
                        if data.get("status") != "success":
                            logger.warning(f"Primary API status not success: {data}")
                            continue
                        return data.get("video_url") if is_video else data.get("audio_url")
            except Exception as e:
                logger.warning(f"Primary API error (attempt {attempt}): {e}")
                await asyncio.sleep(1)
        return None

    # ---------- FALLBACK API (External) ----------
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
                params = {"url": vid_id, "type": "video" if is_video else "audio"}
                async with session.get(f"{current_api}/download", params=params, timeout=60) as resp:
                    if resp.status != 200:
                        logger.error(f"Fallback token API returned {resp.status}")
                        return None
                    data = await resp.json()
                    token = data.get("download_token")
                    if not token:
                        logger.error("No download_token in fallback response")
                        return None

                stream_url = f"{current_api}/stream/{vid_id}?type={'video' if is_video else 'audio'}"
                headers = {"X-Download-Token": token}
                async with session.get(stream_url, headers=headers, timeout=self.download_timeout) as resp:
                    if resp.status != 200:
                        logger.error(f"Fallback stream API returned {resp.status}")
                        return None
                    async with aiofiles.open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(16384):
                            await f.write(chunk)

                if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                    return file_path
                else:
                    logger.error("Fallback download produced invalid file")
        except Exception as e:
            logger.error(f"Fallback API download failed: {e}")
        return None

    # ---------- ULTIMATE FALLBACK: yt-dlp ----------
    async def _ytdlp_download(self, vid_id: str, is_video: bool) -> Optional[str]:
        if not YTDLP_AVAILABLE:
            logger.warning("yt-dlp not available; install it for a reliable fallback.")
            return None

        url = f"https://www.youtube.com/watch?v={vid_id}"
        output_template = f"downloads/{vid_id}.%(ext)s"
        os.makedirs("downloads", exist_ok=True)

        # FIX: 'extract_audio' / 'audio_format' are not real yt-dlp option
        # keys (the correct key is 'extractaudio', and codec belongs on the
        # postprocessor). They were being silently ignored before. Building
        # the postprocessor list up front and dropping the invalid keys.
        if is_video:
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
                'postprocessors': [],
                'socket_timeout': 30,
                'retries': 5,
            }
        else:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'socket_timeout': 30,
                'retries': 5,
            }

        try:
            def download_sync():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    for ext_check in ["mp4", "m4a", "mp3", "webm"]:
                        path = f"downloads/{vid_id}.{ext_check}"
                        if os.path.exists(path) and os.path.getsize(path) > 2048:
                            return path
                    if info.get('requested_downloads'):
                        for d in info['requested_downloads']:
                            if os.path.exists(d['filepath']) and os.path.getsize(d['filepath']) > 2048:
                                return d['filepath']
                    return None

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, download_sync)
            if result:
                return result
            else:
                logger.error("yt-dlp download did not produce a valid file")
        except Exception as e:
            logger.error(f"yt-dlp download error: {e}")
        return None

    # ---------- MAIN DOWNLOAD (with full fallback chain) ----------
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
        """
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

        # 2. Primary API (download then upload)
        logger.info(f"🔄 Attempting primary download for {vid_id}")
        try:
            direct_url = await self.get_api_url(vid_id, is_video_request)
            if direct_url:
                ext = "mp4" if is_video_request else "m4a"
                file_path = os.path.join("downloads", f"{vid_id}.{ext}")
                os.makedirs("downloads", exist_ok=True)
                async with aiohttp.ClientSession() as session:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    async with session.get(direct_url, headers=headers, timeout=self.download_timeout) as resp:
                        if resp.status == 200:
                            async with aiofiles.open(file_path, "wb") as f:
                                async for chunk in resp.content.iter_chunked(1048576):
                                    await f.write(chunk)
                            if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                                uploaded = await self._upload_to_cache(vid_id, file_path, title, is_video_request)
                                if uploaded:
                                    return file_path, True
                                else:
                                    logger.warning("Upload failed, but returning local file.")
                                    return file_path, True
                            else:
                                logger.error("Primary download produced invalid file.")
                        else:
                            logger.warning(f"Primary download HTTP {resp.status}")
        except Exception as e:
            logger.error(f"Primary download failed: {e}")

        # 3. Fallback API (external)
        logger.warning(f"⚠️ Switching to fallback API for {vid_id}")
        fallback_file = await self._external_api_download(vid_id, is_video_request)
        if fallback_file:
            uploaded = await self._upload_to_cache(vid_id, fallback_file, title, is_video_request)
            if uploaded:
                return fallback_file, True
            else:
                logger.warning("Fallback upload failed, but returning downloaded file.")
                return fallback_file, True

        # 4. Ultimate fallback: yt-dlp
        logger.warning(f"🔥 Trying yt-dlp as ultimate fallback for {vid_id}")
        ytdlp_file = await self._ytdlp_download(vid_id, is_video_request)
        if ytdlp_file:
            uploaded = await self._upload_to_cache(vid_id, ytdlp_file, title, is_video_request)
            if uploaded:
                return ytdlp_file, True
            else:
                logger.warning("yt-dlp upload failed, but returning downloaded file.")
                return ytdlp_file, True

        # 5. All failed
        logger.error("❌ All download methods failed. Please check logs.")
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
            except Exception:
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
