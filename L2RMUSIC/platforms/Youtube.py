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
YT_API_KEY = "ShrutiBotsTFDOmDYUMaDd6tfRiogD"
YTPROXY = "https://tgapi.xbitcode.com"
PLAYLIST_ID = -1003616869403          # set to None if you don't want caching
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
        self._ensure_cookies()

    def _ensure_cookies(self):
        if not os.path.exists("cookies.txt"):
            cookie_content = os.environ.get("COOKIES_CONTENT")
            if cookie_content:
                with open("cookies.txt", "w") as f:
                    f.write(cookie_content)
                logger.info("✅ cookies.txt written from environment variable.")
            else:
                logger.warning("⚠️ No cookies.txt found. YouTube may block requests.")

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
        if PLAYLIST_ID is None:
            return False
        try:
            if not os.path.exists(file_path) or os.path.getsize(file_path) < 2048:
                logger.warning(f"⚠️ File too small or missing: {file_path}")
                return False
            db_id = f"{vid_id}_video" if is_video else vid_id
            if await trackdb.find_one({"vid_id": db_id}):
                return True
            logger.info(f"📤 Uploading to channel: {title}")
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
                logger.info(f"✅ Upload complete (msg_id={msg.id})")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Upload error: {e}")
            return False

    async def get_cached_file(self, vid_id: str, is_video: bool = False) -> Optional[str]:
        if PLAYLIST_ID is None:
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
            logger.info(f"🔄 Fetching from channel (msg_id={message_id})")
            cached_msg = await app.get_messages(PLAYLIST_ID, message_id)
            if not cached_msg or cached_msg.empty:
                logger.warning("⚠️ Message not found in channel – cleaning DB")
                await trackdb.delete_one({"vid_id": db_id})
                return None
            media = cached_msg.video or cached_msg.audio or cached_msg.document or cached_msg.voice
            if not media:
                logger.warning("⚠️ No media in cached message")
                return None
            file_id = media.file_id
            file_path = await app.download_media(file_id, file_name=temp_path)
            if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                return file_path
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except (ValueError, KeyError) as e:
            # Invalid peer ID – channel may be deleted/bot removed
            logger.warning(f"⚠️ Cached channel invalid, removing DB entry: {e}")
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
            return None
        try:
            headers = {"x-api-key": YT_API_KEY}
            async with aiohttp.ClientSession() as session:
                api_url = f"{YTPROXY}/info/{vid_id}"
                async with session.get(api_url, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    if data.get("status") != "success":
                        return None
                    return data.get("video_url") if is_video else data.get("audio_url")
        except Exception as e:
            logger.error(f"❌ Primary API error: {e}")
            return None

    async def _external_api_download(self, vid_id: str, is_video: bool) -> Optional[str]:
        global YOUR_API_URL
        if not YOUR_API_URL:
            await load_api_url()
        current_api = YOUR_API_URL or FALLBACK_API_URL
        ext = "mp4" if is_video else "mp3"
        file_path = os.path.join(self._downloads_dir, f"{vid_id}.{ext}")
        try:
            async with aiohttp.ClientSession() as session:
                params = {"url": vid_id, "type": "video" if is_video else "audio"}
                async with session.get(f"{current_api}/download", params=params, timeout=30) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    token = data.get("download_token")
                    if not token:
                        return None
                logger.info(f"🛡️ Using fallback API for {vid_id}")
                stream_url = f"{current_api}/stream/{vid_id}?type={'video' if is_video else 'audio'}"
                headers = {"X-Download-Token": token}
                timeout = aiohttp.ClientTimeout(total=600 if is_video else 300)
                async with session.get(stream_url, headers=headers, timeout=timeout) as stream_resp:
                    if stream_resp.status != 200:
                        return None
                    async with aiofiles.open(file_path, mode='wb') as f:
                        async for chunk in stream_resp.content.iter_chunked(16384):
                            await f.write(chunk)
                if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                    return file_path
                else:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    return None
        except Exception as e:
            logger.error(f"❌ Fallback API failed: {e}")
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
        cookiefile = "cookies.txt" if os.path.exists("cookies.txt") else None
        if not cookiefile:
            logger.warning("⚠️ No cookies.txt – yt-dlp may fail")
        common_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 3,
            'fragment_retries': 3,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'add_metadata': True,
        }
        if cookiefile:
            common_opts['cookiefile'] = cookiefile

        if is_video:
            ydl_opts = {
                **common_opts,
                'format': 'best[ext=mp4]',
                'outtmpl': os.path.join(self._downloads_dir, f"{vid_id}.mp4"),
            }
        else:
            ydl_opts = {
                **common_opts,
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(self._downloads_dir, f"{vid_id}.%(ext)s"),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

        logger.info(f"⬇️ yt-dlp download: {title}")
        for attempt in range(3):
            try:
                loop = asyncio.get_running_loop()
                def download_sync():
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
                logger.error(f"❌ yt-dlp attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2)
        logger.error(f"❌ yt-dlp failed after 3 attempts for {vid_id}")
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

        # 1. Try cache
        cached = await self.get_cached_file(vid_id, is_video=is_video_request)
        if cached:
            return cached, False

        # 2. Download via primary / fallback / yt-dlp
        filepath = None

        # a) Primary API
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
                logger.error(f"❌ Primary API download failed: {e}")
                if 'temp_file' in locals() and os.path.exists(temp_file):
                    os.remove(temp_file)

        # b) Fallback API
        if not filepath:
            filepath = await self._external_api_download(vid_id, is_video_request)

        # c) yt-dlp
        if not filepath:
            filepath = await self._download_with_ytdlp(vid_id, is_video_request, title or vid_id)

        if not filepath:
            raise Exception(f"No audio/video source found for: {vid_id}")

        # 3. Upload to cache
        await self._upload_to_cache(vid_id, filepath, title or vid_id, is_video_request)

        return filepath, False

    # --- Utility methods (unchanged) ---
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
        return None        except Exception as e:
            logger.error(f"❌ Upload error: {e}")
            return False

    # ---- Retrieve from cache (channel → local file) ----
    async def get_cached_file(self, vid_id: str, is_video: bool = False) -> Optional[str]:
        if PLAYLIST_ID is None:
            return None

        db_id = f"{vid_id}_video" if is_video else vid_id

        # 1. Check local download folder first
        local_path = self._find_file(vid_id)
        if local_path:
            return local_path

        # 2. Check MongoDB for channel message
        doc = await trackdb.find_one({"vid_id": db_id})
        if not doc or "message_id" not in doc:
            return None

        message_id = doc['message_id']
        temp_path = os.path.join(self._downloads_dir, f"{vid_id}.mp4")

        try:
            logger.info(f"🔄 Fetching from channel (msg_id={message_id})")
            cached_msg = await app.get_messages(PLAYLIST_ID, message_id)
            if not cached_msg or cached_msg.empty:
                logger.warning("⚠️ Message not found in channel – cleaning DB")
                await trackdb.delete_one({"vid_id": db_id})
                return None

            media = None
            if cached_msg.video:
                media = cached_msg.video.file_id
            elif cached_msg.audio:
                media = cached_msg.audio.file_id
            elif cached_msg.document:
                media = cached_msg.document.file_id
            elif cached_msg.voice:
                media = cached_msg.voice.file_id

            if not media:
                logger.warning("⚠️ No media in the cached message")
                return None

            file_path = await app.download_media(media, file_name=temp_path)
            if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                return file_path

            if os.path.exists(temp_path):
                os.remove(temp_path)

        except Exception as e:
            logger.error(f"❌ Cache retrieval failed: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return None

    # ---- Primary API (XBIT) ----
    async def get_api_url(self, vid_id: str, is_video: bool) -> Optional[str]:
        if not YT_API_KEY or not YTPROXY:
            return None
        try:
            headers = {"x-api-key": YT_API_KEY}
            async with aiohttp.ClientSession() as session:
                api_url = f"{YTPROXY}/info/{vid_id}"
                async with session.get(api_url, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    if data.get("status") != "success":
                        return None
                    return data.get("video_url") if is_video else data.get("audio_url")
        except Exception as e:
            logger.error(f"❌ Primary API error: {e}")
            return None

    # ---- Fallback API (external download service) ----
    async def _external_api_download(self, vid_id: str, is_video: bool) -> Optional[str]:
        global YOUR_API_URL
        if not YOUR_API_URL:
            await load_api_url()
        current_api = YOUR_API_URL or FALLBACK_API_URL

        ext = "mp4" if is_video else "mp3"
        file_path = os.path.join(self._downloads_dir, f"{vid_id}.{ext}")

        try:
            async with aiohttp.ClientSession() as session:
                params = {"url": vid_id, "type": "video" if is_video else "audio"}
                async with session.get(f"{current_api}/download", params=params, timeout=30) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    token = data.get("download_token")
                    if not token:
                        return None

                logger.info(f"🛡️ Using fallback API for {vid_id}")
                stream_url = f"{current_api}/stream/{vid_id}?type={'video' if is_video else 'audio'}"
                headers = {"X-Download-Token": token}
                timeout = aiohttp.ClientTimeout(total=600 if is_video else 300)

                async with session.get(stream_url, headers=headers, timeout=timeout) as stream_resp:
                    if stream_resp.status != 200:
                        return None
                    async with aiofiles.open(file_path, mode='wb') as f:
                        async for chunk in stream_resp.content.iter_chunked(16384):
                            await f.write(chunk)

                if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                    return file_path
                else:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    return None

        except Exception as e:
            logger.error(f"❌ Fallback API failed: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return None

    # ---- yt-dlp fallback ----
    async def _download_with_ytdlp(self, vid_id: str, is_video: bool, title: str) -> Optional[str]:
        if yt_dlp is None:
            logger.error("❌ yt-dlp not installed")
            return None

        cookiefile = "cookies.txt" if os.path.exists("cookies.txt") else None
        if not cookiefile:
            logger.warning("⚠️ No cookies.txt – YouTube may block the download.")

        common_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'add_metadata': True,
            'extractor_args': {
                'youtube': {
                    'skip': ['hls', 'dash'],
                }
            }
        }

        if cookiefile:
            common_opts['cookiefile'] = cookiefile

        if is_video:
            ydl_opts = {
                **common_opts,
                'format': 'best[ext=mp4]',
                'outtmpl': os.path.join(self._downloads_dir, f"{vid_id}.mp4"),
            }
        else:
            ydl_opts = {
                **common_opts,
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(self._downloads_dir, f"{vid_id}.%(ext)s"),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

        logger.info(f"⬇️ Downloading via yt-dlp ({'with' if cookiefile else 'without'} cookies): {title}")

        for attempt in range(3):
            try:
                loop = asyncio.get_running_loop()

                def download_sync():
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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

                if result and os.path.exists(result) and os.path.getsize(result) > 2048:
                    logger.info(f"✅ yt-dlp success: {result} 🎉")
                    return result

                for f in os.listdir(self._downloads_dir):
                    if f.startswith(vid_id):
                        try:
                            os.remove(os.path.join(self._downloads_dir, f))
                        except:
                            pass

            except Exception as e:
                logger.error(f"❌ yt-dlp attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2)
                for f in os.listdir(self._downloads_dir):
                    if f.startswith(vid_id):
                        try:
                            os.remove(os.path.join(self._downloads_dir, f))
                        except:
                            pass

        logger.error(f"❌ yt-dlp failed after 3 attempts for {vid_id}")
        return None

    # ---- 🎯 MAIN DOWNLOAD (cache‑first, synchronous upload) ----
    async def download(
        self,
        link: str,
        mystic,  # kept for compatibility
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[str, bool]:
        """
        Returns (file_path, False) – always a local file.
        The file is guaranteed to be uploaded to the cache channel after this call.
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

        # 1. Try cache (channel → local file)
        cached = await self.get_cached_file(vid_id, is_video=is_video_request)
        if cached:
            return cached, False

        # 2. Download from primary / fallback / yt-dlp
        filepath = None

        # a) Primary API (download URL)
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
                logger.error(f"❌ Primary API download failed: {e}")
                if 'temp_file' in locals() and os.path.exists(temp_file):
                    os.remove(temp_file)

        # b) Fallback external API
        if not filepath:
            filepath = await self._external_api_download(vid_id, is_video_request)

        # c) yt-dlp (last resort)
        if not filepath:
            filepath = await self._download_with_ytdlp(vid_id, is_video_request, title or vid_id)

        if not filepath:
            raise Exception(f"No audio/video source found for: {vid_id}")

        # 3. Upload to cache channel (synchronous – ensures cache is ready for next time)
        await self._upload_to_cache(vid_id, filepath, title or vid_id, is_video_request)

        return filepath, False

    # ---- 📋 Utility methods (unchanged) ----
    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        return []

    async def _get_video_details(self, link: str, limit: int = 1) -> Optional[dict]:
        try:
            results = VideosSearch(link, limit=limit)
            search_results = (await results.next()).get("result", [])
            for result in search_results:
                return result
            search = CustomSearch(query=link, searchPreferences="EgIYAw==", limit=1)
            for res in (await search.next()).get("result", []):
                return res
            return None
        except Exception as e:
            logger.error(f"❌ Video details error: {e}")
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
        return result["title"], result["duration"], seconds, result["thumbnails"][0]["url"].split("?")[0], result["id"]

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
        return result["thumbnails"][0]["url"].split("?")[0] if result else None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = await self._get_video_details(link)
        if not result:
            raise ValueError("No suitable video found")
        return {
            "title": result["title"],
            "link": result["link"],
            "vidid": result["id"],
            "duration_min": result["duration"],
            "thumb": result["thumbnails"][0]["url"].split("?")[0]
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
        return selected["title"], selected["duration"], selected["thumbnails"][0]["url"].split("?")[0], selected["id"]

    async def url(self, message_1: Message) -> Optional[str]:
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
