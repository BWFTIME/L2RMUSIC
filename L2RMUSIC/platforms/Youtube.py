import asyncio
import os
import re
from typing import Union
import aiohttp
import aiofiles
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch, CustomSearch
from L2RMUSIC import LOGGER, app 
from L2RMUSIC.utils.formatters import time_to_seconds
from motor.motor_asyncio import AsyncIOMotorClient

# --- ADDED: yt-dlp import ---
try:
    import yt_dlp
except ImportError:
    yt_dlp = None
    LOGGER(__name__).warning("yt-dlp not installed. Install it to enable direct download fallback.")

# --- CONFIG VALUES ---
YT_API_KEY = "ShrutiBotsPg57ZpYO5WK2OovGuF8f"
YTPROXY = "https://tgapi.xbitcode.com"
PLAYLIST_ID = -1003616869403
MONGO_DB_URI = "mongodb+srv://L2RKING:BWF_MUSIC1@l2rking.1ikcd.mongodb.net/?retryWrites=true&w=majority"
LIMIT_SECONDS = 900

# --- FALLBACK API CONFIG ---
YOUR_API_URL = None
FALLBACK_API_URL = "https://shrutibots.site"

logger = LOGGER(__name__)

# --- DATABASE CONNECTION ---
_mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
mongodb = _mongo_async_.L2RMUSIC
trackdb = mongodb.track_cache

# --- LOAD FALLBACK API URL ---
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

# Start loading API URL in background
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

    def _find_file(self, vid_id):
        if not os.path.exists("downloads"): 
            return None
        for ext in ["m4a", "mp4", "mp3", "webm"]:
            filepath = f"downloads/{vid_id}.{ext}"
            if os.path.exists(filepath):
                if os.path.getsize(filepath) > 2048:
                    return os.path.abspath(filepath)
                else:
                    try: 
                        os.remove(filepath)
                    except: 
                        pass
        return None

    # --- UNIVERSAL UPLOAD (Saves Message ID for Multiple Bots) ---
    async def _upload_to_cache(self, vid_id, file_path, title, is_video):
        try:
            if not os.path.exists(file_path): 
                return
            
            db_id = f"{vid_id}_video" if is_video else vid_id
            exists = await trackdb.find_one({"vid_id": db_id})
            if exists: 
                return

            logger.info(f"📤 Uploading to Channel: {title}")
            cap = f"**Song:** {title}\n**ID:** `{vid_id}`\n**Saved by:** {app.me.mention}"
            
            msg = None
            try:
                if is_video:
                    msg = await app.send_video(PLAYLIST_ID, file_path, caption=cap, supports_streaming=True)
                else:
                    msg = await app.send_audio(PLAYLIST_ID, file_path, caption=cap, title=title)
            except Exception as up_err:
                logger.error(f"Dump Channel Upload Failed (Check Admin Permissions): {up_err}")
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

    # --- UNIVERSAL RETRIEVAL (Reads Message ID & Fetches Fresh File ID) ---
    async def get_cached_file(self, vid_id: str, is_video: bool = False):
        db_id = f"{vid_id}_video" if is_video else vid_id
        local_path = self._find_file(vid_id)
        if local_path: 
            return local_path

        doc = await trackdb.find_one({"vid_id": db_id})
        
        if doc and "message_id" in doc:
            message_id = doc['message_id']
            temp_path = os.path.join("downloads", f"{vid_id}.mp4")
            
            try:
                logger.info(f"🔄 Fetching from Channel (Msg ID: {message_id})")
                
                try:
                    cached_msg = await app.get_messages(PLAYLIST_ID, message_id)
                except Exception as peer_err:
                    logger.warning(f"Cache Peer Error (Skipping Cache): {peer_err}")
                    return None
                
                if not cached_msg or cached_msg.empty:
                    logger.warning("Message not found/deleted in channel, cleaning DB.")
                    await trackdb.delete_one({"vid_id": db_id})
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
                logger.error(f"Cache Retrieval Failed: {e}")
                if os.path.exists(temp_path): 
                    os.remove(temp_path)
        
        return None

    # --- PRIMARY API LOGIC ---
    async def get_api_url(self, vid_id, is_video):
        try:
            if not YT_API_KEY or not YTPROXY: 
                return None
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
            logger.error(f"API Error: {e}")
            return None

    # --- FALLBACK API LOGIC ---
    async def _external_api_download(self, vid_id, is_video):
        global YOUR_API_URL
        if not YOUR_API_URL:
            await load_api_url()
        
        current_api = YOUR_API_URL or FALLBACK_API_URL
        
        ext = "mp4" if is_video else "mp3"
        type_str = "video" if is_video else "audio"
        file_path = os.path.join("downloads", f"{vid_id}.{ext}")

        # Ensure downloads folder exists
        if not os.path.exists("downloads"): 
            os.makedirs("downloads")

        try:
            async with aiohttp.ClientSession() as session:
                # Request download token
                params = {"url": vid_id, "type": type_str}
                async with session.get(
                    f"{current_api}/download",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200: 
                        return None
                    data = await response.json()
                    download_token = data.get("download_token")
                    if not download_token: 
                        return None

                logger.info(f"🛡️ Using Fallback API for {vid_id}")
                stream_url = f"{current_api}/stream/{vid_id}?type={type_str}"
                
                async with session.get(
                    stream_url,
                    headers={"X-Download-Token": download_token},
                    timeout=aiohttp.ClientTimeout(total=600 if is_video else 300)
                ) as file_response:
                    if file_response.status != 200: 
                        return None
                    
                    async with aiofiles.open(file_path, mode='wb') as f:
                        async for chunk in file_response.content.iter_chunked(16384):
                            await f.write(chunk)
                    
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                        return file_path
                    else:
                        # Delete empty/partial file
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        return None
        except Exception as e:
            logger.error(f"Fallback API Failed: {e}")
            # Clean up partial file
            if os.path.exists(file_path):
                try: 
                    os.remove(file_path)
                except: 
                    pass
            return None

    # --- YT-DLP FALLBACK (DIRECT DOWNLOAD) ---
    async def _download_with_ytdlp(self, vid_id, is_video, title):
        """Last resort: Direct download using yt-dlp (requires FFmpeg)"""
        if yt_dlp is None:
            logger.error("yt-dlp not installed. Cannot use this fallback.")
            return None

        # Ensure downloads folder exists
        os.makedirs("downloads", exist_ok=True)

        # Set output template
        ext = "mp4" if is_video else "mp3"
        output_path = os.path.join("downloads", f"{vid_id}.{ext}")

        # yt-dlp options
        if is_video:
            ydl_opts = {
                'format': 'best[ext=mp4]',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
        else:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join("downloads", f"{vid_id}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

        logger.info(f"⬇️ Downloading via yt-dlp: {title or vid_id}")

        try:
            loop = asyncio.get_running_loop()
            
            def download_sync():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={vid_id}"])
                # After download, check if file exists
                # For audio, the file might have .mp3 or .m4a extension due to postprocessor
                # We'll search for any file starting with vid_id in downloads
                for f in os.listdir("downloads"):
                    if f.startswith(vid_id) and os.path.getsize(os.path.join("downloads", f)) > 2048:
                        # If it's an audio and extension is not .mp3, rename to .mp3
                        if not is_video and not f.endswith(".mp3"):
                            # The postprocessor should have converted, but just in case
                            final_path = os.path.join("downloads", f"{vid_id}.mp3")
                            if f != final_path:
                                os.rename(os.path.join("downloads", f), final_path)
                            return final_path
                        else:
                            return os.path.join("downloads", f)
                return None

            result_path = await loop.run_in_executor(None, download_sync)
            
            if result_path and os.path.exists(result_path) and os.path.getsize(result_path) > 2048:
                logger.info(f"✅ yt-dlp download successful: {result_path}")
                return result_path
            else:
                # Cleanup partial files
                for f in os.listdir("downloads"):
                    if f.startswith(vid_id):
                        try: os.remove(os.path.join("downloads", f))
                        except: pass
                return None

        except Exception as e:
            logger.error(f"yt-dlp failed: {e}")
            # Cleanup
            for f in os.listdir("downloads"):
                if f.startswith(vid_id):
                    try: os.remove(os.path.join("downloads", f))
                    except: pass
            return None

    # --- BACKGROUND PROCESS ---
    async def _background_process(self, vid_id, link, title, is_video, duration_sec=None):
        if duration_sec is None:
            try:
                dur_str = await self.duration(link)
                duration_sec = time_to_seconds(dur_str)
            except: 
                duration_sec = 0
            
        if duration_sec > LIMIT_SECONDS:
            return

        if not os.path.exists("downloads"): 
            os.makedirs("downloads")
        if self._find_file(vid_id): 
            return

        filepath = os.path.join("downloads", f"{vid_id}.mp4")

        try:
            api_direct_url = await self.get_api_url(vid_id, is_video)
            if api_direct_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_direct_url) as resp:
                        if resp.status == 200:
                            async with aiofiles.open(filepath, mode='wb') as f:
                                async for chunk in resp.content.iter_chunked(1048576):
                                    await f.write(chunk)
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 2048:
                                await self._upload_to_cache(vid_id, filepath, title, is_video)
                                return 
        except: 
            pass

    # --- MAIN DOWNLOAD FUNCTION (FIXED WITH YT-DLP FALLBACK) ---
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
            if "v=" in link: 
                vid_id = link.split('v=')[-1].split('&')[0]
            else: 
                vid_id = link.split('/')[-1]

        is_video_request = bool(video or songvideo)

        # 1. CHECK CACHE
        try:
            cached_path = await self.get_cached_file(vid_id, is_video=is_video_request)
            if cached_path: 
                return cached_path, True
        except Exception as e:
            logger.error(f"Cache check skipped due to error: {e}")

        # 2. TRY PRIMARY API (XBIT) - STREAM + BACKGROUND CACHE
        try:
            api_url = await self.get_api_url(vid_id, is_video_request)
            if api_url:
                logger.info(f"🚀 API Stream: {title or vid_id}")
                asyncio.create_task(self._background_process(vid_id, link, title or vid_id, is_video_request))
                return api_url, True
        except Exception as e:
            logger.error(f"Primary API Failed: {e}")

        # 3. IF PRIMARY FAILS -> TRIGGER FALLBACK API
        logger.warning(f"⚠️ Switching to Fallback API for {vid_id}...")
        
        fallback_file = await self._external_api_download(vid_id, is_video_request)
        
        if fallback_file:
            logger.info(f"✅ Fallback Download Success: {title or vid_id}")
            asyncio.create_task(self._upload_to_cache(vid_id, fallback_file, title or vid_id, is_video_request))
            return fallback_file, True

        # 4. LAST RESORT: Try yt-dlp direct download
        logger.warning(f"🔄 Primary & Fallback APIs failed. Trying yt-dlp for {vid_id}...")
        ytdlp_file = await self._download_with_ytdlp(vid_id, is_video_request, title or vid_id)
        
        if ytdlp_file:
            logger.info(f"✅ yt-dlp Success: {title or vid_id}")
            asyncio.create_task(self._upload_to_cache(vid_id, ytdlp_file, title or vid_id, is_video_request))
            return ytdlp_file, True
        
        # ❌ सब कुछ फेल - अब Exception throw करो
        logger.error("❌ All APIs AND yt-dlp Failed. No source found.")
        raise Exception(f"No audio/video source found for: {vid_id}")

    # --- UTILS (unchanged) ---
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
        except: 
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
        return {"title": result["title"], "link": result["link"], "vidid": result["id"], "duration_min": result["duration"], "thumb": result["thumbnails"][0]["url"].split("?")[0]}, result["id"]

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
        return None                    media_file = cached_msg.document.file_id
                elif cached_msg.voice: 
                    media_file = cached_msg.voice.file_id

                if media_file:
                    file = await app.download_media(media_file, file_name=temp_path)
                    if file and os.path.exists(file) and os.path.getsize(file) > 2048:
                        return file
                
                if os.path.exists(temp_path): 
                    os.remove(temp_path)
            
            except Exception as e:
                logger.error(f"Cache Retrieval Failed: {e}")
                if os.path.exists(temp_path): 
                    os.remove(temp_path)
        
        return None

    # --- PRIMARY API LOGIC ---
    async def get_api_url(self, vid_id, is_video):
        try:
            if not YT_API_KEY or not YTPROXY: 
                return None
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
            logger.error(f"API Error: {e}")
            return None

    # --- FALLBACK API LOGIC ---
    async def _external_api_download(self, vid_id, is_video):
        global YOUR_API_URL
        if not YOUR_API_URL:
            await load_api_url()
        
        current_api = YOUR_API_URL or FALLBACK_API_URL
        
        ext = "mp4" if is_video else "mp3"
        type_str = "video" if is_video else "audio"
        file_path = os.path.join("downloads", f"{vid_id}.{ext}")

        # Ensure downloads folder exists
        if not os.path.exists("downloads"): 
            os.makedirs("downloads")

        try:
            async with aiohttp.ClientSession() as session:
                # Request download token
                params = {"url": vid_id, "type": type_str}
                async with session.get(
                    f"{current_api}/download",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200: 
                        return None
                    data = await response.json()
                    download_token = data.get("download_token")
                    if not download_token: 
                        return None

                logger.info(f"🛡️ Using Fallback API for {vid_id}")
                stream_url = f"{current_api}/stream/{vid_id}?type={type_str}"
                
                async with session.get(
                    stream_url,
                    headers={"X-Download-Token": download_token},
                    timeout=aiohttp.ClientTimeout(total=600 if is_video else 300)
                ) as file_response:
                    if file_response.status != 200: 
                        return None
                    
                    async with aiofiles.open(file_path, mode='wb') as f:
                        async for chunk in file_response.content.iter_chunked(16384):
                            await f.write(chunk)
                    
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 2048:
                        return file_path
                    else:
                        # Delete empty/partial file
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        return None
        except Exception as e:
            logger.error(f"Fallback API Failed: {e}")
            # Clean up partial file
            if os.path.exists(file_path):
                try: 
                    os.remove(file_path)
                except: 
                    pass
            return None

    # --- BACKGROUND PROCESS ---
    async def _background_process(self, vid_id, link, title, is_video, duration_sec=None):
        if duration_sec is None:
            try:
                dur_str = await self.duration(link)
                duration_sec = time_to_seconds(dur_str)
            except: 
                duration_sec = 0
            
        if duration_sec > LIMIT_SECONDS:
            return

        if not os.path.exists("downloads"): 
            os.makedirs("downloads")
        if self._find_file(vid_id): 
            return

        filepath = os.path.join("downloads", f"{vid_id}.mp4")

        try:
            api_direct_url = await self.get_api_url(vid_id, is_video)
            if api_direct_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_direct_url) as resp:
                        if resp.status == 200:
                            async with aiofiles.open(filepath, mode='wb') as f:
                                async for chunk in resp.content.iter_chunked(1048576):
                                    await f.write(chunk)
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 2048:
                                await self._upload_to_cache(vid_id, filepath, title, is_video)
                                return 
        except: 
            pass

    # --- MAIN DOWNLOAD FUNCTION (FIXED) ---
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
            if "v=" in link: 
                vid_id = link.split('v=')[-1].split('&')[0]
            else: 
                vid_id = link.split('/')[-1]

        is_video_request = bool(video or songvideo)

        # 1. CHECK CACHE
        try:
            cached_path = await self.get_cached_file(vid_id, is_video=is_video_request)
            if cached_path: 
                return cached_path, True
        except Exception as e:
            logger.error(f"Cache check skipped due to error: {e}")

        # 2. TRY PRIMARY API (XBIT) - STREAM + BACKGROUND CACHE
        try:
            api_url = await self.get_api_url(vid_id, is_video_request)
            if api_url:
                logger.info(f"🚀 API Stream: {title or vid_id}")
                asyncio.create_task(self._background_process(vid_id, link, title or vid_id, is_video_request))
                return api_url, True
        except Exception as e:
            logger.error(f"Primary API Failed: {e}")

        # 3. IF PRIMARY FAILS -> TRIGGER FALLBACK API
        logger.warning(f"⚠️ Switching to Fallback API for {vid_id}...")
        
        fallback_file = await self._external_api_download(vid_id, is_video_request)
        
        if fallback_file:
            logger.info(f"✅ Fallback Download Success: {title or vid_id}")
            asyncio.create_task(self._upload_to_cache(vid_id, fallback_file, title or vid_id, is_video_request))
            return fallback_file, True
        
        # ❌ ALL FAILED – Raise Exception instead of returning None
        logger.error("❌ All APIs Failed. No source found.")
        raise Exception(f"No audio/video source found for: {vid_id}")

    # --- UTILS (unchanged) ---
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
        except: 
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
        return {"title": result["title"], "link": result["link"], "vidid": result["id"], "duration_min": result["duration"], "thumb": result["thumbnails"][0]["url"].split("?")[0]}, result["id"]

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
