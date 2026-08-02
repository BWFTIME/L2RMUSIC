import asyncio
import os
import re
from typing import Union, Optional, Tuple

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

# --- CONFIG ---
YT_API_KEY = "30DxNexGenBots0055e5"
YTPROXY = "https://tgapi.xbitcode.com"
PLAYLIST_ID = -1001859664687          # Updated for https://t.me/YouTubedatabase (Bot must be admin here)
MONGO_DB_URI = "mongodb+srv://L2RKING:BWF_MUSIC1@l2rking.1ikcd.mongodb.net/?retryWrites=true&w=majority"
LIMIT_SECONDS = 900

FALLBACK_API_URL = "https://shrutibots.site"
YOUR_API_URL = None

_mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
mongodb = _mongo_async_.L2RMUSIC
trackdb = mongodb.track_cache


async def load_api_url():
    global YOUR_API_URL
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://pastebin.com/raw/rLsBhAQa",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    YOUR_API_URL = (await resp.text()).strip()
                    logger.info(f"✅ Fallback API URL loaded: {YOUR_API_URL}")
                else:
                    YOUR_API_URL = FALLBACK_API_URL
    except Exception as e:
        logger.warning(f"⚠️ Could not load fallback URL, using default: {e}")
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
        self._downloads_dir = "downloads"
        os.makedirs(self._downloads_dir, exist_ok=True)
        self._cache_disabled = False
        self._ensure_cookies()

    def _ensure_cookies(self):
        """Force‑write cookies from env var and validate."""
        content = os.environ.get("COOKIES_CONTENT", "")
        if not content:
            logger.error("❌ COOKIES_CONTENT environment variable is NOT SET or EMPTY.")
            return

        # Check if it looks like a Netscape cookies file
        if "# Netscape HTTP Cookie File" not in content and ".youtube.com" not in content:
            logger.error("❌ COOKIES_CONTENT does not look like a valid cookies file!")
            return

        # Always overwrite with latest content
        with open("cookies.txt", "w") as f:
            f.write(content)

        if os.path.exists("cookies.txt") and os.path.getsize("cookies.txt") > 50:
            logger.info("✅ cookies.txt successfully created from COOKIES_CONTENT")
        else:
            logger.error("❌ cookies.txt was written but is too small – check COOKIES_CONTENT")

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

    async def _upload_to_cache(self, vid_id: str, file_path: str, title: str, is_video: bool) -> bool:
        if PLAYLIST_ID is None or self._cache_disabled:
            return False
        try:
            if not os.path.exists(file_path) or os.path.getsize(file_path) < 2048:
                return False
            db_id = f"{vid_id}_video" if is_video else vid_id
            if await trackdb.find_one({"vid_id": db_id}):
                return True
            logger.info(f"📤 Uploading to channel (YouTubedatabase): {title}")
            caption = f"**🎵 Song:** {title}\n**🆔 ID:** `{vid_id}`\n**💾 Saved by:** {app.me.mention}"
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
                logger.error(f"❌ Channel invalid or bot not admin – disabling cache permanently: {e}")
                self._cache_disabled = True
                return False
            except asyncio.TimeoutError:
                logger.error("⏰ Upload timed out")
                return False
            except Exception as e:
                logger.error(f"❌ Upload failed: {e}")
                return False
            
            if msg and msg.id:
                await trackdb.update_one(
                    {"vid_id": db_id},
                    {"$set": {"message_id": msg.id, "title": title, "type": "video" if is_video else "audio"}},
                    upsert=True
                )
                logger.info(f"✅ Upload complete toTubedatabase (msg_id={msg.id})")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Upload error: {e}")
            return False

    async def get_cached_file(self, vid_id: str, is_video: bool = False) -> Optional[str]:
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
            logger.info(f"🔄 Fetching from Tubedatabase channel (msg_id={message_id})")
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
            logger.warning(f"⚠️ Cached channel invalid, disabling cache: {e}")
            self._cache_disabled = True
            await trackdb.delete_one({"vid_id": db_id})
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            logger.error(f"❌ Cache retrieval failed: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
        return None

    async def get_api_url(self, vid_id: str, is_video: bool) -> Optional[str]:
        if not YT_API_KEY or not YTPROXY:
            logger.error("❌ Primary API: YT_API_KEY or YTPROXY missing")
            return None
        try:
            headers = {"x-api-key": YT_API_KEY}
            async with aiohttp.ClientSession() as session:
                api_url = f"{YTPROXY}/info/{vid_id}"
                async with session.get(api_url, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ Primary API returned status {resp.status}")
                        return None
                    data = await resp.json()
                    if data.get("status") != "success":
                        logger.warning(f"⚠️ Primary API status not success: {data}")
                        return None
                    url = data.get("video_url") if is_video else data.get("audio_url")
                    if url:
                        logger.info(f"✅ Got URL from primary API for {vid_id}")
                    else:
                        logger.warning("⚠️ Primary API response missing URL")
                    return url
        except Exception as e:
            logger.error(f"❌ Primary API exception: {e}")
            return None

    async def _external_api_download(self, vid_id: str, is_video: bool) -> Optional[str]:
        global YOUR_API_URL
        if not YOUR_API_URL:
            await load_api_url()
        current_api = YOUR_API_URL or FALLBACK_API_URL
        logger.info(f"🛡️ Trying fallback API: {current_api}")
        ext = "mp4" if is_video else "mp3"
        file_path = os.path.join(self._downloads_dir, f"{vid_id}.{ext}")
        try:
            async with aiohttp.ClientSession() as session:
                params = {"url": vid_id, "type": "video" if is_video else "audio"}
                async with session.get(f"{current_api}/download", params=params, timeout=30) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ Fallback token request failed with status {resp.status}")
                        return None
                    data = await resp.json()
                    token = data.get("download_token")
                    if not token:
                        logger.warning("⚠️ Fallback response missing download_token")
                        return None
                logger.info(f"📥 Downloading via fallback stream for {vid_id}")
                stream_url = f"{current_api}/stream/{vid_id}?type={'video' if is_video else 'audio'}"
                headers = {"X-Download-Token": token}
                timeout = aiohttp.ClientTimeout(total=600 if is_video else 300)
                async with session.get(stream_url, headers=headers, timeout=timeout) as stream_resp:
                    if stream_resp.status != 200:
                        logger.warning(f"⚠️ Fallback stream returned status {stream_resp.status}")
                        return None
                    async with aiofiles.open(file_path, mode='wb') as f:
                        async for chunk in stream_resp.content.iter_chunked(16384):
                            await f.write(chunk)
                if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                    logger.info(f"✅ Fallback download success: {file_path}")
                    return file_path
                else:
                    logger.warning("⚠️ Fallback downloaded file is too small or missing")
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    return None
        except Exception as e:
            logger.error(f"❌ Fallback API exception: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return None

    async def _download_with_ytdlp(self, vid_id: str, is_video: bool, title: str) -> Optional[str]:
        if yt_dlp is None:
            logger.error("❌ yt-dlp not installed")
            return None

        cookies_exist = os.path.exists("cookies.txt") and os.path.getsize("cookies.txt") > 50

        # Strategy 1: with cookies (if available)
        if cookies_exist:
            logger.info("🍪 yt-dlp with cookies")
            result = await self._try_ytdlp(vid_id, is_video, title, use_cookies=True, android_client=False)
            if result:
                return result
        else:
            logger.error("❌ No cookies.txt – yt-dlp will likely fail. Set COOKIES_CONTENT properly!")

        # Strategy 2: Android client, no cookies
        logger.info("📱 yt-dlp with Android client (no cookies)")
        result = await self._try_ytdlp(vid_id, is_video, title, use_cookies=False, android_client=True)
        if result:
            return result

        # Strategy 3: Web client, no cookies
        logger.info("🌐 yt-dlp web client (no cookies)")
        result = await self._try_ytdlp(vid_id, is_video, title, use_cookies=False, android_client=False)
        if result:
            return result

        logger.error(f"❌ All yt-dlp strategies failed for {vid_id}")
        return None

    async def _try_ytdlp(self, vid_id, is_video, title, use_cookies, android_client):
        try:
            loop = asyncio.get_running_loop()
            opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'socket_timeout': 30,
                'retries': 3,
                'fragment_retries': 3,
                'user_agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36' if android_client else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'referer': 'https://www.youtube.com/',
                'add_metadata': True,
            }
            if use_cookies:
                opts['cookiefile'] = 'cookies.txt'
            if android_client:
                opts['extractor_args'] = {'youtube': {'player_client': ['android']}}

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
                                os.rename(full, new_path)
                                return new_path
                            return full
                return None

            result = await loop.run_in_executor(None, download_sync)
            if result:
                logger.info(f"✅ yt-dlp success: {result}")
                return result
        except Exception as e:
            logger.warning(f"⚠️ yt-dlp strategy failed: {e}")
        return None

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
    ) -> Tuple[str, bool]:
        if videoid:
            vid_id = link
            link = self.base + link
        else:
            if "v=" in link:
                vid_id = link.split('v=')[-1].split('&')[0]
            else:
                vid_id = link.split('/')[-1]

        is_video_request = bool(video or songvideo)
        filepath = None

        # 1. Cache
        cached = await self.get_cached_file(vid_id, is_video=is_video_request)
        if cached:
            logger.info(f"✅ Using cached file from Tubedatabase: {cached}")
            return cached, False

        # 2. Primary API
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
                            else:
                                os.remove(temp_file)
            except Exception as e:
                logger.error(f"❌ Primary download failed: {e}")
                if 'temp_file' in locals() and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass

        # 3. Fallback API
        if not filepath:
            filepath = await self._external_api_download(vid_id, is_video_request)

        # 4. yt-dlp
        if not filepath:
            filepath = await self._download_with_ytdlp(vid_id, is_video_request, title or vid_id)

        if not filepath:
            raise Exception(f"No audio/video source found for: {vid_id}")

        # 5. Upload to cache channel (YouTubedatabase)
        asyncio.create_task(self._upload_to_cache(vid_id, filepath, title or vid_id, is_video_request))

        return filepath, False

    # --- Utility methods ---
    async def playlist(self, link, limit, user_id, videoid=None):
        return []

    async def _get_video_details(self, link: str, limit=1):
        try:
            results = VideosSearch(link, limit=limit)
            search_results = (await results.next()).get("result", [])
            for r in search_results:
                return r
            search = CustomSearch(query=link, searchPreferences="EgIYAw==", limit=1)
            for r in (await search.next()).get("result", []):
                return r
        except Exception as e:
            logger.error(f"❌ Video details error: {e}")
        return None

    async def details(self, link, videoid=None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await self._get_video_details(link)
        if not result:
            raise ValueError("No suitable video found")
        dur = result.get("duration", "0:00")
        seconds = 0 if "live" in str(dur).lower() else int(time_to_seconds(dur) or 0)
        return result["title"], result["duration"], seconds, result["thumbnails"][0]["url"].split("?")[0], result["id"]

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
