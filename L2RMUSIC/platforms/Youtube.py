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

# --- CONFIG ---
YTPROXY = getenv("YTPROXY_URL", "https://tgapi.xbitcode.com")
YT_API_KEY = getenv("YT_API_KEY", "xbit_GjLUhA7Xsu_5Dr_xBdFZLr8LzorcKIkK")
PLAYLIST_ID = -1001859664687          # Your Channel: https://t.me/YouTubedatabase (Bot must be admin here)
MONGO_DB_URI = getenv("MONGO_DB_URI", "mongodb+srv://L2RKING:BWF_MUSIC1@l2rking.1ikcd.mongodb.net/?retryWrites=true&w=majority")
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
        """Force-write cookies from env var and validate."""
        content = os.environ.get("COOKIES_CONTENT", "")
        if not content:
            logger.warning("⚠️ COOKIES_CONTENT environment variable is NOT SET. yt-dlp might face bot verification errors.")
            return

        with open("cookies.txt", "w") as f:
            f.write(content)

        if os.path.exists("cookies.txt") and os.path.getsize("cookies.txt") > 20:
            logger.info("✅ cookies.txt successfully created from COOKIES_CONTENT")
        else:
            logger.warning("⚠️ cookies.txt was written but is too small.")

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
                logger.info(f"✅ Upload complete to Tubedatabase (msg_id={msg.id})")
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
            return None
        try:
            headers = {"x-api-key": YT_API_KEY}
            async with aiohttp.ClientSession() as session:
                api_url = f"{YTPROXY}/info/{vid_id}"
                async with session.get(api_url, headers=headers, timeout=7) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    if data.get("status") != "success":
                        return None
                    return data.get("video_url") if is_video else data.get("audio_url")
        except Exception:
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
                async with session.get(f"{current_api}/download", params=params, timeout=15) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    token = data.get("download_token")
                    if not token:
                        return None
                
                stream_url = f"{current_api}/stream/{vid_id}?type={'video' if is_video else 'audio'}"
                headers = {"X-Download-Token": token}
                async with session.get(stream_url, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as stream_resp:
                    if stream_resp.status != 200:
                        return None
                    async with aiofiles.open(file_path, mode='wb') as f:
                        async for chunk in stream_resp.content.iter_chunked(16384):
                            await f.write(chunk)
                if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                    return file_path
                if os.path.exists(file_path):
                    os.remove(file_path)
        except Exception:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
        return None

    async def _download_with_ytdlp(self, vid_id: str, is_video: bool, title: str) -> Optional[str]:
        if yt_dlp is None:
            return None

        clients_to_try = [
            {'use_cookies': True, 'client': 'default'},
            {'use_cookies': False, 'client': 'android'},
            {'use_cookies': False, 'client': 'ios'},
            {'use_cookies': False, 'client': 'web'}
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
                'retries': 3,
                'fragment_retries': 3,
                'add_metadata': True,
            }

            cookies_exist = os.path.exists("cookies.txt") and os.path.getsize("cookies.txt") > 20
            if use_cookies and cookies_exist:
                opts['cookiefile'] = 'cookies.txt'
            elif use_cookies and not cookies_exist:
                return None

            if client_type == 'android':
                opts['extractor_args'] = {'youtube': {'player_client': ['android']}}
                opts['user_agent'] = 'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36'
            elif client_type == 'ios':
                opts['extractor_args'] = {'youtube': {'player_client': ['ios']}}
                opts['user_agent'] = 'com.google.ios.youtube/18.19.1 (iPhone14,3; U; CPU iOS 16_5 like Mac OS X)'
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
                logger.info(f"✅ yt-dlp success using [{client_type}]: {result}")
                return result
        except Exception:
            pass
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

        # 1. Check Cache Channel first
        cached = await self.get_cached_file(vid_id, is_video=is_video_request)
        if cached:
            return cached, False

        # 2. Try Primary API
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
            except Exception:
                pass

        # 3. Try Fallback API
        if not filepath:
            filepath = await self._external_api_download(vid_id, is_video_request)

        # 4. Try yt-dlp
        if not filepath:
            filepath = await self._download_with_ytdlp(vid_id, is_video_request, title or vid_id)

        if not filepath:
            raise Exception(f"No audio/video source found for: {vid_id}")

        # 5. Background Upload to Cache Channel (YouTubedatabase)
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
        except Exception:
            pass
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
