import asyncio
import os
import re
from typing import Union, Optional, Tuple
from os import getenv

import aiohttp
import aiofiles
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch, CustomSearch
from motor.motor_asyncio import AsyncIOMotorClient

from L2RMUSIC import LOGGER, app
from L2RMUSIC.utils.formatters import time_to_seconds

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

logger = LOGGER(__name__)

# --- CONFIGURATION (Environment overrides) ---
YTPROXY = getenv("YTPROXY_URL", "https://tgapi.xbitcode.com")
YT_API_KEY = getenv("YT_API_KEY", "xbit_GjLUhA7Xsu_5Dr_xBdFZLr8LzorcKIkK")
PLAYLIST_ID = -1001859664687          # Your channel: https://t.me/YouTubedatabase
MONGO_DB_URI = getenv("MONGO_DB_URI", "mongodb+srv://L2RKING:BWF_MUSIC1@l2rking.1ikcd.mongodb.net/?retryWrites=true&w=majority")
LIMIT_SECONDS = 900

FALLBACK_API_URL = getenv("FALLBACK_API_URL", "https://shrutibots.site")
YOUR_API_URL = None

_mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
mongodb = _mongo_async_.L2RMUSIC
trackdb = mongodb.track_cache

# Create index on 'title' for fast search
async def create_indexes():
    await trackdb.create_index("title", unique=False)
    await trackdb.create_index("vid_id", unique=True)

try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(create_indexes())
    else:
        loop.run_until_complete(create_indexes())
except:
    pass

# ------------------------------------------------------------
async def load_api_url():
    global YOUR_API_URL
    env_url = getenv("FALLBACK_API_URL")
    if env_url:
        YOUR_API_URL = env_url
        logger.info(f"✅ Using fallback API from env: {YOUR_API_URL}")
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://pastebin.com/raw/rLsBhAQa",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    YOUR_API_URL = (await resp.text()).strip()
                    logger.info(f"✅ Fallback API loaded from Pastebin: {YOUR_API_URL}")
                else:
                    YOUR_API_URL = FALLBACK_API_URL
                    logger.warning(f"⚠️ Pastebin returned {resp.status}, using default")
    except Exception as e:
        logger.warning(f"⚠️ Could not load fallback URL, using default: {e}")
        YOUR_API_URL = FALLBACK_API_URL

# Initialize ASAP
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(load_api_url())
    else:
        loop.run_until_complete(load_api_url())
except RuntimeError:
    pass

# ------------------------------------------------------------
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        self._downloads_dir = "downloads"
        os.makedirs(self._downloads_dir, exist_ok=True)
        self._cache_disabled = False
        self._ensure_cookies()

    def _ensure_cookies(self):
        content = os.environ.get("COOKIES_CONTENT", "")
        if not content:
            logger.warning("⚠️ COOKIES_CONTENT not set. yt-dlp may fail with bot errors.")
            return
        try:
            with open("cookies.txt", "w") as f:
                f.write(content)
            if os.path.exists("cookies.txt") and os.path.getsize("cookies.txt") > 20:
                logger.info("✅ cookies.txt created successfully")
            else:
                logger.warning("⚠️ cookies.txt written but seems too small")
        except Exception as e:
            logger.error(f"❌ Failed to write cookies.txt: {e}")

    def _find_file(self, vid_id: str) -> Optional[str]:
        for ext in ["m4a", "mp4", "mp3", "webm"]:
            filepath = os.path.join(self._downloads_dir, f"{vid_id}.{ext}")
            if os.path.exists(filepath):
                if os.path.getsize(filepath) > 2048:
                    return os.path.abspath(filepath)
                else:
                    try:
                        os.remove(filepath)
                    except:
                        pass
        return None

    # ---------- CACHE HANDLING ----------
    async def _upload_to_cache(
        self,
        vid_id: str,
        file_path: str,
        title: str,
        is_video: bool,
        duration: str = None,
        thumb: str = None
    ) -> bool:
        """Upload file to cache channel and store metadata in DB."""
        if PLAYLIST_ID is None or self._cache_disabled:
            return False
        try:
            if not os.path.exists(file_path) or os.path.getsize(file_path) < 2048:
                return False
            db_id = f"{vid_id}_video" if is_video else vid_id

            # Check if already in DB
            if await trackdb.find_one({"vid_id": db_id}):
                return True

            logger.info(f"📤 Uploading to cache channel: {title}")
            caption = (
                f"**🎵 Song:** {title}\n"
                f"**🆔 ID:** `{vid_id}`\n"
                f"**💾 Saved by:** {app.me.mention}"
            )
            try:
                if is_video:
                    msg = await asyncio.wait_for(
                        app.send_video(PLAYLIST_ID, file_path, caption=caption, supports_streaming=True),
                        timeout=180
                    )
                else:
                    msg = await asyncio.wait_for(
                        app.send_audio(PLAYLIST_ID, file_path, caption=caption, title=title),
                        timeout=180
                    )
            except (ValueError, KeyError) as e:
                logger.error(f"❌ Channel invalid or bot not admin – disabling cache: {e}")
                self._cache_disabled = True
                return False
            except asyncio.TimeoutError:
                logger.error("⏰ Upload timed out")
                return False
            except Exception as e:
                logger.error(f"❌ Upload failed: {e}")
                return False

            if msg and msg.id:
                # Store metadata in DB
                doc = {
                    "vid_id": db_id,
                    "message_id": msg.id,
                    "title": title,
                    "type": "video" if is_video else "audio",
                }
                if duration:
                    doc["duration"] = duration
                if thumb:
                    doc["thumb"] = thumb
                await trackdb.update_one(
                    {"vid_id": db_id},
                    {"$set": doc},
                    upsert=True
                )
                logger.info(f"✅ Upload complete (msg_id={msg.id})")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Upload error: {e}")
            return False

    async def get_cached_file(self, vid_id: str, is_video: bool = False) -> Optional[str]:
        """Get file from local or channel cache by video ID."""
        if PLAYLIST_ID is None or self._cache_disabled:
            return None
        db_id = f"{vid_id}_video" if is_video else vid_id
        local_path = self._find_file(vid_id)
        if local_path:
            return local_path

        doc = await trackdb.find_one({"vid_id": db_id})
        if not doc or "message_id" not in doc:
            return None

        message_id = doc['message_id']
        temp_path = os.path.join(self._downloads_dir, f"{vid_id}.mp4")
        try:
            logger.info(f"🔄 Fetching from cache channel (msg_id={message_id})")
            cached_msg = await app.get_messages(PLAYLIST_ID, message_id)
            if not cached_msg or cached_msg.empty:
                await trackdb.delete_one({"vid_id": db_id})
                return None
            media = cached_msg.video or cached_msg.audio or cached_msg.document or cached_msg.voice
            if not media:
                return None
            file_id = media.file_id
            file_path = await app.download_media(file_id, file_name=temp_path)
            if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                return file_path
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except (ValueError, KeyError) as e:
            logger.warning(f"⚠️ Cache channel invalid, disabling: {e}")
            self._cache_disabled = True
            await trackdb.delete_one({"vid_id": db_id})
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            logger.error(f"❌ Cache retrieval failed: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
        return None

    async def _search_cache_by_title(self, query: str) -> Optional[dict]:
        """Search the cache DB by title (case-insensitive). Return metadata if found."""
        if self._cache_disabled or PLAYLIST_ID is None:
            return None
        # Use regex for case-insensitive partial match
        regex = re.compile(query, re.IGNORECASE)
        doc = await trackdb.find_one({"title": {"$regex": regex}})
        if doc:
            vid_id = doc["vid_id"].replace("_video", "").replace("_audio", "")
            # If we have duration/thumb in DB, use them; else try to get from file
            duration = doc.get("duration", "0:00")
            thumb = doc.get("thumb", "")
            title = doc["title"]
            logger.info(f"✅ Found cached song: {title} (ID: {vid_id})")
            return {
                "title": title,
                "duration": duration,
                "seconds": time_to_seconds(duration) if duration != "0:00" else 0,
                "thumb": thumb,
                "vid_id": vid_id,
                "is_video": doc["type"] == "video"
            }
        return None

    # ---------- API DOWNLOAD METHODS ----------
    async def get_api_url(self, vid_id: str, is_video: bool) -> Optional[str]:
        if not YT_API_KEY or not YTPROXY:
            return None
        try:
            headers = {"x-api-key": YT_API_KEY}
            async with aiohttp.ClientSession() as session:
                api_url = f"{YTPROXY}/info/{vid_id}"
                async with session.get(api_url, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ Primary API returned {resp.status}")
                        return None
                    data = await resp.json()
                    if data.get("status") != "success":
                        logger.warning(f"⚠️ Primary API status not success: {data}")
                        return None
                    url = data.get("video_url") if is_video else data.get("audio_url")
                    if url:
                        logger.info(f"✅ Primary API returned URL: {url[:60]}...")
                    return url
        except Exception as e:
            logger.warning(f"⚠️ Primary API error: {e}")
            return None

    async def _external_api_download(self, vid_id: str, is_video: bool) -> Optional[str]:
        global YOUR_API_URL
        if not YOUR_API_URL:
            await load_api_url()

        apis_to_try = [YOUR_API_URL, FALLBACK_API_URL] if YOUR_API_URL != FALLBACK_API_URL else [FALLBACK_API_URL]
        ext = "mp4" if is_video else "mp3"
        file_path = os.path.join(self._downloads_dir, f"{vid_id}.{ext}")

        for api_base in apis_to_try:
            try:
                logger.info(f"🔄 Trying fallback API: {api_base}")
                async with aiohttp.ClientSession() as session:
                    params = {"url": vid_id, "type": "video" if is_video else "audio"}
                    async with session.get(f"{api_base}/download", params=params, timeout=15) as resp:
                        if resp.status != 200:
                            logger.warning(f"⚠️ {api_base} /download -> {resp.status}")
                            continue
                        data = await resp.json()
                        token = data.get("download_token")
                        if not token:
                            logger.warning(f"⚠️ {api_base} no download_token")
                            continue

                    stream_url = f"{api_base}/stream/{vid_id}?type={'video' if is_video else 'audio'}"
                    headers = {"X-Download-Token": token}
                    async with session.get(stream_url, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as stream_resp:
                        if stream_resp.status != 200:
                            logger.warning(f"⚠️ {api_base} /stream -> {stream_resp.status}")
                            continue
                        async with aiofiles.open(file_path, mode='wb') as f:
                            async for chunk in stream_resp.content.iter_chunked(16384):
                                await f.write(chunk)

                    if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                        logger.info(f"✅ Downloaded via fallback API: {api_base}")
                        return file_path
                    else:
                        if os.path.exists(file_path):
                            os.remove(file_path)
            except Exception as e:
                logger.warning(f"⚠️ Fallback API {api_base} error: {e}")
                continue
        return None

    # ---------- YT-DLP WITH MULTIPLE STRATEGIES ----------
    async def _download_with_ytdlp(self, vid_id: str, is_video: bool, title: str) -> Optional[str]:
        if yt_dlp is None:
            logger.warning("⚠️ yt-dlp not installed")
            return None

        clients_to_try = [
            {'use_cookies': True, 'client': 'android'},
            {'use_cookies': True, 'client': 'ios'},
            {'use_cookies': False, 'client': 'android'},
            {'use_cookies': False, 'client': 'ios'},
        ]

        for config in clients_to_try:
            result = await self._try_ytdlp(vid_id, is_video, title, config['use_cookies'], config['client'])
            if result:
                return result

        logger.error(f"❌ All yt-dlp strategies failed for {vid_id}")
        return None

    async def _try_ytdlp(self, vid_id, is_video, title, use_cookies, client_type):
        try:
            loop = asyncio.get_running_loop()
            opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'socket_timeout': 30,
                'retries': 5,
                'fragment_retries': 5,
                'add_metadata': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'ios'] if client_type in ['android', 'ios'] else ['web'],
                        'skip': ['dash', 'hls'],
                    }
                }
            }

            cookies_exist = os.path.exists("cookies.txt") and os.path.getsize("cookies.txt") > 20
            if use_cookies and cookies_exist:
                opts['cookiefile'] = 'cookies.txt'
            elif use_cookies and not cookies_exist:
                return None

            if client_type == 'android':
                opts['user_agent'] = 'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36'
            elif client_type == 'ios':
                opts['user_agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1'
            else:
                opts['user_agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

            if is_video:
                opts['format'] = 'best[ext=mp4]'
                opts['outtmpl'] = os.path.join(self._downloads_dir, f"{vid_id}.mp4")
            else:
                opts['format'] = 'bestaudio/best'
                opts['outtmpl'] = os.path.join(self._downloads_dir, f"{vid_id}.%(ext)s")
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]

            def download_sync():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={vid_id}"])
                for f in os.listdir(self._downloads_dir):
                    if f.startswith(vid_id):
                        full = os.path.join(self._downloads_dir, f)
                        if os.path.getsize(full) > 2048:
                            if not is_video and not f.endswith(".mp3"):
                                new_path = os.path.join(self._downloads_dir, f"{vid_id}.mp3")
                                if os.path.exists(new_path):
                                    os.remove(new_path)
                                os.rename(full, new_path)
                                return new_path
                            return full
                return None

            result = await loop.run_in_executor(None, download_sync)
            if result:
                logger.info(f"✅ yt-dlp success [{client_type}]: {result}")
                return result
        except Exception as e:
            logger.debug(f"yt-dlp {client_type} failed: {e}")
        return None

    # ---------- MAIN DOWNLOAD ----------
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
        duration: str = None,
        thumb: str = None,
    ) -> Tuple[str, bool]:
        """
        Download a song/video.
        If videoid is provided, use it; else treat link as a search query and first check cache.
        Returns (filepath, is_cached).
        """
        # If videoid not given and link is not a URL, treat as search query
        if not videoid and not re.search(self.regex, link):
            # Search cache by title
            cached = await self._search_cache_by_title(link)
            if cached:
                # We found it in cache – return the file via get_cached_file
                vid_id = cached["vid_id"]
                is_video_request = cached.get("is_video", False)
                filepath = await self.get_cached_file(vid_id, is_video=is_video_request)
                if filepath:
                    logger.info(f"✅ Playing from cache: {filepath}")
                    return filepath, True
                else:
                    # File not available, fallback to normal download
                    logger.warning("⚠️ Cached metadata found but file missing – re-downloading")
                    # We'll still use the vid_id to download
                    videoid = vid_id
                    # Use cached title, duration, thumb for upload later
                    title = cached["title"]
                    duration = cached.get("duration")
                    thumb = cached.get("thumb")
            # If not cached, proceed with YouTube search (done by caller via details)

        # Extract video ID
        if videoid:
            vid_id = videoid
            link = self.base + vid_id
        else:
            if "v=" in link:
                vid_id = link.split('v=')[-1].split('&')[0]
            else:
                vid_id = link.split('/')[-1]

        is_video_request = bool(video or songvideo)
        filepath = None

        # 1. Check cache channel by vid_id
        cached_file = await self.get_cached_file(vid_id, is_video=is_video_request)
        if cached_file:
            logger.info(f"✅ Retrieved from cache (by ID): {cached_file}")
            return cached_file, True

        # Ensure we have a proper title (actual song name)
        if not title or title == vid_id:
            # Fetch title from YouTube
            try:
                title, _, _, _, _ = await self.details(vid_id, videoid=vid_id)
            except Exception as e:
                logger.warning(f"Could not fetch title: {e}")
                title = vid_id

        # 2. Try primary API
        logger.info("🔄 Trying primary API...")
        api_url = await self.get_api_url(vid_id, is_video_request)
        if api_url:
            try:
                ext = "mp4" if is_video_request else "mp3"
                temp_file = os.path.join(self._downloads_dir, f"{vid_id}.{ext}")
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, timeout=300) as resp:
                        if resp.status == 200:
                            async with aiofiles.open(temp_file, 'wb') as f:
                                async for chunk in resp.content.iter_chunked(1048576):
                                    await f.write(chunk)
                            if os.path.getsize(temp_file) > 2048:
                                filepath = temp_file
                                logger.info(f"✅ Downloaded via primary API: {filepath}")
                            else:
                                os.remove(temp_file)
                                logger.warning("⚠️ Primary API file too small, removed")
            except Exception as e:
                logger.warning(f"⚠️ Primary API download error: {e}")

        # 3. Fallback API
        if not filepath:
            logger.info("🔄 Trying fallback API...")
            filepath = await self._external_api_download(vid_id, is_video_request)
            if filepath:
                logger.info(f"✅ Downloaded via fallback API: {filepath}")

        # 4. yt-dlp
        if not filepath:
            logger.info("🔄 Trying yt-dlp...")
            filepath = await self._download_with_ytdlp(vid_id, is_video_request, title)
            if filepath:
                logger.info(f"✅ Downloaded via yt-dlp: {filepath}")

        if not filepath:
            raise Exception(f"❌ No source found for {vid_id} (all methods failed)")

        # Upload to cache in background with metadata
        asyncio.create_task(
            self._upload_to_cache(vid_id, filepath, title, is_video_request, duration, thumb)
        )

        return filepath, False

    # ---------- DETAILS (with cache search) ----------
    async def details(self, link, videoid=None):
        """
        Get video details.
        If videoid not given and link is a search query, first search cache by title.
        """
        if videoid:
            link = self.base + link
        elif not re.search(self.regex, link):
            # It's a search query – check cache first
            cached = await self._search_cache_by_title(link)
            if cached:
                return (
                    cached["title"],
                    cached["duration"],
                    cached["seconds"],
                    cached["thumb"],
                    cached["vid_id"]
                )

        # If not cached or it's a URL, proceed with YouTube search
        if "&" in link:
            link = link.split("&")[0]
        result = await self._get_video_details(link)
        if not result:
            raise ValueError("No suitable video found")
        dur = result.get("duration", "0:00")
        seconds = 0 if "live" in str(dur).lower() else int(time_to_seconds(dur) or 0)
        return result["title"], result["duration"], seconds, result["thumbnails"][0]["url"].split("?")[0], result["id"]

    async def _get_video_details(self, link: str, limit=1):
        try:
            results = VideosSearch(link, limit=limit)
            search_results = (await results.next()).get("result", [])
            for r in search_results:
                return r
            search = CustomSearch(query=link, searchPreferences="EgIYAw==", limit=1)
            for r in (await search.next()).get("result", []):
                return r
        except Exception:
            pass
        return None

    # ---------- UTILITY METHODS ----------
    async def playlist(self, link, limit, user_id, videoid=None):
        return []

    async def exists(self, link, videoid=None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def title(self, link, videoid=None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        r = await self._get_video_details(link)
        return r["title"] if r else None

    async def duration(self, link, videoid=None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        r = await self._get_video_details(link)
        return r["duration"] if r else None

    async def thumbnail(self, link, videoid=None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        r = await self._get_video_details(link)
        return r["thumbnails"][0]["url"].split("?")[0] if r else None

    async def track(self, link, videoid=None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        r = await self._get_video_details(link)
        if not r:
            raise ValueError("No suitable video found")
        return {
            "title": r["title"],
            "link": r["link"],
            "vidid": r["id"],
            "duration_min": r["duration"],
            "thumb": r["thumbnails"][0]["url"].split("?")[0]
        }, r["id"]

    async def formats(self, link, videoid=None):
        return [], link

    async def slider(self, link, query_type, videoid=None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        search = VideosSearch(link, limit=10)
        results = (await search.next()).get("result", [])
        if not results:
            raise ValueError("No videos found")
        sel = results[query_type] if query_type < len(results) else results[0]
        return sel["title"], sel["duration"], sel["thumbnails"][0]["url"].split("?")[0], sel["id"]

    async def url(self, message_1: Message) -> Optional[str]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for msg in messages:
            if msg.entities:
                for e in msg.entities:
                    if e.type == MessageEntityType.URL:
                        text = msg.text or msg.caption
                        return text[e.offset: e.offset + e.length]
            elif msg.caption_entities:
                for e in msg.caption_entities:
                    if e.type == MessageEntityType.TEXT_LINK:
                        return e.url
        return None
