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

# --- yt-dlp fallback ---
try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# --- Logger (CORRECTED) ---
logger = LOGGER(__name__)   # <-- use function call, not getChild

# --- CONFIG ---
YT_API_KEY = "ShrutiBotsPg57ZpYO5WK2OovGuF8f"
YTPROXY = "https://tgapi.xbitcode.com"
PLAYLIST_ID = -1003616869403
MONGO_DB_URI = "mongodb+srv://L2RKING:BWF_MUSIC1@l2rking.1ikcd.mongodb.net/?retryWrites=true&w=majority"
LIMIT_SECONDS = 900

FALLBACK_API_URL = "https://shrutibots.site"
YOUR_API_URL = None

# --- MongoDB ---
_mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
mongodb = _mongo_async_.L2RMUSIC
trackdb = mongodb.track_cache


# --- Load fallback API URL ---
async def load_api_url():
    global YOUR_API_URL
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://pastebin.com/raw/rLsBhAQa", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    YOUR_API_URL = (await resp.text()).strip()
                    logger.info(f"Fallback API URL loaded: {YOUR_API_URL}")
                else:
                    YOUR_API_URL = FALLBACK_API_URL
    except Exception as e:
        logger.warning(f"Could not load fallback URL, using default: {e}")
        YOUR_API_URL = FALLBACK_API_URL


# Start loading in background (non‑blocking)
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

    # ---- Local file finder ----
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

    # ---- Upload to cache channel (with retries) ----
    async def _upload_to_cache(self, vid_id: str, file_path: str, title: str, is_video: bool) -> bool:
        try:
            if not os.path.exists(file_path) or os.path.getsize(file_path) < 2048:
                logger.warning(f"File too small or missing: {file_path}")
                return False

            db_id = f"{vid_id}_video" if is_video else vid_id
            if await trackdb.find_one({"vid_id": db_id}):
                return True   # already cached

            logger.info(f"📤 Uploading to channel: {title}")
            caption = f"**Song:** {title}\n**ID:** `{vid_id}`\n**Saved by:** {app.me.mention}"

            # Try sending with a timeout
            try:
                if is_video:
                    msg = await asyncio.wait_for(
                        app.send_video(PLAYLIST_ID, file_path, caption=caption, supports_streaming=True),
                        timeout=120
                    )
                else:
                    msg = await asyncio.wait_for(
                        app.send_audio(PLAYLIST_ID, file_path, caption=caption, title=title),
                        timeout=120
                    )
            except asyncio.TimeoutError:
                logger.error("Upload timed out – channel might be slow")
                return False
            except Exception as e:
                logger.error(f"Upload failed: {e}")
                return False

            if msg and msg.id:
                await trackdb.update_one(
                    {"vid_id": db_id},
                    {"$set": {"message_id": msg.id, "title": title, "type": "video" if is_video else "audio"}},
                    upsert=True
                )
                logger.info(f"✅ Upload complete (msg_id={msg.id}): {title}")
                return True
            return False

        except Exception as e:
            logger.error(f"Upload error: {e}")
            return False

    # ---- Retrieve from cache ----
    async def get_cached_file(self, vid_id: str, is_video: bool = False) -> Optional[str]:
        db_id = f"{vid_id}_video" if is_video else vid_id

        # 1. Check local download folder
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
                logger.warning("Message not found in channel – cleaning DB")
                await trackdb.delete_one({"vid_id": db_id})
                return None

            # Determine media file_id
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
                logger.warning("No media in the cached message")
                return None

            # Download media
            file_path = await app.download_media(media, file_name=temp_path)
            if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                return file_path

            # If download failed, clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)

        except Exception as e:
            logger.error(f"Cache retrieval failed: {e}")
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
            logger.error(f"Primary API error: {e}")
            return None

    # ---- Fallback API (download via external service) ----
    async def _external_api_download(self, vid_id: str, is_video: bool) -> Optional[str]:
        global YOUR_API_URL
        if not YOUR_API_URL:
            await load_api_url()
        current_api = YOUR_API_URL or FALLBACK_API_URL

        ext = "mp4" if is_video else "mp3"
        file_path = os.path.join(self._downloads_dir, f"{vid_id}.{ext}")

        try:
            async with aiohttp.ClientSession() as session:
                # 1. Request download token
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
            logger.error(f"Fallback API failed: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return None

    # ---- yt-dlp fallback (with optional cookies) ----
    async def _download_with_ytdlp(self, vid_id: str, is_video: bool, title: str) -> Optional[str]:
        if yt_dlp is None:
            logger.error("yt-dlp not installed")
            return None

        # Check if cookies file exists; if not, we omit it
        cookiefile = "cookies.txt" if os.path.exists("cookies.txt") else None

        if is_video:
            ydl_opts = {
                'format': 'best[ext=mp4]',
                'outtmpl': os.path.join(self._downloads_dir, f"{vid_id}.mp4"),
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
        else:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(self._downloads_dir, f"{vid_id}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

        if cookiefile:
            ydl_opts['cookiefile'] = cookiefile

        logger.info(f"⬇️ Downloading via yt-dlp{'' if cookiefile else ' (no cookies)'}: {title}")

        try:
            loop = asyncio.get_running_loop()

            def download_sync():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={vid_id}"])
                # Find downloaded file
                for f in os.listdir(self._downloads_dir):
                    if f.startswith(vid_id):
                        full = os.path.join(self._downloads_dir, f)
                        if os.path.getsize(full) > 2048:
                            # If audio, ensure .mp3 extension
                            if not is_video and not f.endswith(".mp3"):
                                new_path = os.path.join(self._downloads_dir, f"{vid_id}.mp3")
                                os.rename(full, new_path)
                                return new_path
                            else:
                                return full
                return None

            result = await loop.run_in_executor(None, download_sync)

            if result and os.path.exists(result) and os.path.getsize(result) > 2048:
                logger.info(f"✅ yt-dlp success: {result}")
                return result

            # Clean up partial files
            for f in os.listdir(self._downloads_dir):
                if f.startswith(vid_id):
                    try:
                        os.remove(os.path.join(self._downloads_dir, f))
                    except:
                        pass
            return None

        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            for f in os.listdir(self._downloads_dir):
                if f.startswith(vid_id):
                    try:
                        os.remove(os.path.join(self._downloads_dir, f))
                    except:
                        pass
            return None

    # ---- Background caching process ----
    async def _background_process(self, vid_id: str, link: str, title: str, is_video: bool, duration_sec: Optional[int] = None):
        if duration_sec is None:
            try:
                dur_str = await self.duration(link, videoid=True)  # link is already video ID
                duration_sec = time_to_seconds(dur_str) if dur_str else 0
            except:
                duration_sec = 0

        if duration_sec > LIMIT_SECONDS:
            logger.info(f"Skipping cache for {title} (duration {duration_sec}s > limit)")
            return

        # Already downloaded?
        if self._find_file(vid_id):
            return

        filepath = os.path.join(self._downloads_dir, f"{vid_id}.mp4")
        try:
            # Try primary API stream
            api_url = await self.get_api_url(vid_id, is_video)
            if api_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, timeout=300) as resp:
                        if resp.status == 200:
                            async with aiofiles.open(filepath, mode='wb') as f:
                                async for chunk in resp.content.iter_chunked(1048576):
                                    await f.write(chunk)
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 2048:
                                await self._upload_to_cache(vid_id, filepath, title, is_video)
                                return
        except Exception as e:
            logger.warning(f"Background primary download failed: {e}")

        # If primary fails, try fallback API (download)
        fallback_file = await self._external_api_download(vid_id, is_video)
        if fallback_file:
            await self._upload_to_cache(vid_id, fallback_file, title, is_video)

        # If all fail, yt-dlp will be attempted on the fly during main download,
        # but we don't run it here to avoid duplicate work.

    # ---- MAIN DOWNLOAD (with all fallbacks) ----
    async def download(
        self,
        link: str,
        mystic,  # kept for compatibility but not used
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[str, bool]:
        """
        Returns: (file_path_or_url, is_direct_stream)
        If is_direct_stream is True, the returned string is a direct URL (to be streamed).
        Otherwise it's a local file path.
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

        # 1. Try cache
        try:
            cached = await self.get_cached_file(vid_id, is_video=is_video_request)
            if cached:
                return cached, False
        except Exception as e:
            logger.error(f"Cache error: {e}")

        # 2. Primary API (stream)
        try:
            api_url = await self.get_api_url(vid_id, is_video_request)
            if api_url:
                logger.info(f"🚀 Streaming via primary API: {title or vid_id}")
                # Start background caching (don't await)
                asyncio.create_task(self._background_process(vid_id, link, title or vid_id, is_video_request))
                return api_url, True
        except Exception as e:
            logger.error(f"Primary API error: {e}")

        # 3. Fallback API (download)
        logger.warning(f"⚠️ Using fallback API for {vid_id}...")
        fallback_file = await self._external_api_download(vid_id, is_video_request)
        if fallback_file:
            logger.info(f"✅ Fallback download success: {title or vid_id}")
            asyncio.create_task(self._upload_to_cache(vid_id, fallback_file, title or vid_id, is_video_request))
            return fallback_file, False

        # 4. yt-dlp (final resort)
        logger.warning(f"🔄 Trying yt-dlp for {vid_id}...")
        ytdlp_file = await self._download_with_ytdlp(vid_id, is_video_request, title or vid_id)
        if ytdlp_file:
            logger.info(f"✅ yt-dlp success: {title or vid_id}")
            asyncio.create_task(self._upload_to_cache(vid_id, ytdlp_file, title or vid_id, is_video_request))
            return ytdlp_file, False

        # 5. All failed
        logger.error(f"❌ All download methods failed for {vid_id}")
        raise Exception(f"No audio/video source found for: {vid_id}")

    # ---- Utility methods (unchanged, but with fixes) ----
    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        # Not implemented – returns empty list
        return []

    async def _get_video_details(self, link: str, limit: int = 1) -> Optional[dict]:
        try:
            results = VideosSearch(link, limit=limit)
            search_results = (await results.next()).get("result", [])
            for result in search_results:
                return result
            # Fallback with CustomSearch
            search = CustomSearch(query=link, searchPreferences="EgIYAw==", limit=1)
            for res in (await search.next()).get("result", []):
                return res
            return None
        except Exception as e:
            logger.error(f"Video details error: {e}")
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
                )
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False

        if msg and msg.id:
            await trackdb.update_one(
                {"vid_id": db_id},
                {"$set": {"message_id": msg.id, "title": title, "type": "video" if is_video else "audio"}},
                upsert=True
            )
            logger.info(f"✅ Upload complete (msg_id={msg.id}): {title}")
            return True
        return False

    # ---- Retrieve from cache (with robust error handling) ----
    async def get_cached_file(self, vid_id: str, is_video: bool = False) -> Optional[str]:
        if not await check_cache_channel():
            return None

        db_id = f"{vid_id}_video" if is_video else vid_id

        # 1. Check local downloads folder
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
                logger.warning("Message not found in channel – cleaning DB entry")
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
                logger.warning("No media in cached message")
                return None

            file_path = await app.download_media(media, file_name=temp_path)
            if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                return file_path

            if os.path.exists(temp_path):
                os.remove(temp_path)

        except PeerIdInvalid:
            logger.error(f"Peer ID invalid for channel {PLAYLIST_ID}. Disabling cache.")
            global _CACHE_AVAILABLE
            _CACHE_AVAILABLE = False
            await trackdb.delete_one({"vid_id": db_id})
            return None
        except Exception as e:
            logger.error(f"Cache retrieval failed: {e}")
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
            logger.error(f"Primary API error: {e}")
            return None

    # ---- Fallback API (download via external service) ----
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
            logger.error(f"Fallback API failed: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            return None

    # ---- yt-dlp fallback (with optional cookies) ----
    async def _download_with_ytdlp(self, vid_id: str, is_video: bool, title: str) -> Optional[str]:
        if yt_dlp is None:
            logger.error("yt-dlp not installed")
            return None

        cookiefile = "cookies.txt" if os.path.exists("cookies.txt") else None
        if not cookiefile:
            logger.warning("No cookies.txt found – yt-dlp may fail due to YouTube bot detection.")

        if is_video:
            ydl_opts = {
                'format': 'best[ext=mp4]',
                'outtmpl': os.path.join(self._downloads_dir, f"{vid_id}.mp4"),
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
        else:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(self._downloads_dir, f"{vid_id}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

        if cookiefile:
            ydl_opts['cookiefile'] = cookiefile

        logger.info(f"⬇️ Downloading via yt-dlp{'' if cookiefile else ' (no cookies)'}: {title}")

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
                logger.info(f"✅ yt-dlp success: {result}")
                return result

            # Clean up partial files
            for f in os.listdir(self._downloads_dir):
                if f.startswith(vid_id):
                    try:
                        os.remove(os.path.join(self._downloads_dir, f))
                    except:
                        pass
            return None

        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            for f in os.listdir(self._downloads_dir):
                if f.startswith(vid_id):
                    try:
                        os.remove(os.path.join(self._downloads_dir, f))
                    except:
                        pass
            return None

    # ---- Background caching process ----
    async def _background_process(self, vid_id: str, link: str, title: str, is_video: bool, duration_sec: Optional[int] = None):
        if duration_sec is None:
            try:
                dur_str = await self.duration(link, videoid=True)
                duration_sec = time_to_seconds(dur_str) if dur_str else 0
            except:
                duration_sec = 0

        if duration_sec > LIMIT_SECONDS:
            logger.info(f"Skipping cache for {title} (duration {duration_sec}s > limit)")
            return

        if self._find_file(vid_id):
            return

        filepath = os.path.join(self._downloads_dir, f"{vid_id}.mp4")
        try:
            api_url = await self.get_api_url(vid_id, is_video)
            if api_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, timeout=300) as resp:
                        if resp.status == 200:
                            async with aiofiles.open(filepath, mode='wb') as f:
                                async for chunk in resp.content.iter_chunked(1048576):
                                    await f.write(chunk)
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 2048:
                                await self._upload_to_cache(vid_id, filepath, title, is_video)
                                return
        except Exception as e:
            logger.warning(f"Background primary download failed: {e}")

        fallback_file = await self._external_api_download(vid_id, is_video)
        if fallback_file:
            await self._upload_to_cache(vid_id, fallback_file, title, is_video)

    # ---- MAIN DOWNLOAD ----
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
        try:
            cached = await self.get_cached_file(vid_id, is_video=is_video_request)
            if cached:
                return cached, False
        except Exception as e:
            logger.error(f"Cache error: {e}")

        # 2. Primary API (stream)
        try:
            api_url = await self.get_api_url(vid_id, is_video_request)
            if api_url:
                logger.info(f"🚀 Streaming via primary API: {title or vid_id}")
                asyncio.create_task(self._background_process(vid_id, link, title or vid_id, is_video_request))
                return api_url, True
        except Exception as e:
            logger.error(f"Primary API error: {e}")

        # 3. Fallback API (download)
        logger.warning(f"⚠️ Using fallback API for {vid_id}...")
        fallback_file = await self._external_api_download(vid_id, is_video_request)
        if fallback_file:
            logger.info(f"✅ Fallback download success: {title or vid_id}")
            asyncio.create_task(self._upload_to_cache(vid_id, fallback_file, title or vid_id, is_video_request))
            return fallback_file, False

        # 4. yt-dlp
        logger.warning(f"🔄 Trying yt-dlp for {vid_id}...")
        ytdlp_file = await self._download_with_ytdlp(vid_id, is_video_request, title or vid_id)
        if ytdlp_file:
            logger.info(f"✅ yt-dlp success: {title or vid_id}")
            asyncio.create_task(self._upload_to_cache(vid_id, ytdlp_file, title or vid_id, is_video_request))
            return ytdlp_file, False

        logger.error(f"❌ All download methods failed for {vid_id}")
        raise Exception(f"No audio/video source found for: {vid_id}")

    # ---- Utility methods (with cache-first search) ----
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
            logger.error(f"Video details error: {e}")
            return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        # If link is a search query (not a URL), try cache first
        if not videoid and not re.search(self.regex, link):
            cached = await self._search_cache_by_title(link)
            if cached:
                # Use cached vid_id to get details (could fetch from DB, but we'll get from YouTube for now)
                # We'll return the title from DB and fetch other metadata from YouTube or fake it.
                # Better: we store duration, thumbnail in DB? For simplicity, we'll fetch from YouTube using the vid_id.
                try:
                    # We have vid_id, get details from YouTube
                    return await self.details(self.base + cached["vid_id"], videoid=True)
                except Exception as e:
                    logger.error(f"Error fetching details for cached vid {cached['vid_id']}: {e}")
                    # Fall back to YouTube search if fails
                    pass

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
        # If link is a search query (not a URL), try cache first
        if not videoid and not re.search(self.regex, link):
            cached = await self._search_cache_by_title(link)
            if cached:
                # Return a fake result with the cached title and vid_id
                # We'll need a thumbnail – we can fetch from YouTube or use a placeholder.
                # For simplicity, we'll fetch from YouTube using the vid_id.
                try:
                    # Get details from YouTube for that vid_id
                    result, _ = await self.track(self.base + cached["vid_id"], videoid=True)
                    return result, cached["vid_id"]
                except Exception as e:
                    logger.error(f"Error fetching details for cached vid {cached['vid_id']}: {e}")
                    # Fall back to YouTube search for the query
                    pass

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
