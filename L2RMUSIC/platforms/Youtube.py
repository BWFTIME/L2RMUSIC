# FIX BY SHONA @THECDERQUEEN
import os
import re
import asyncio
import aiohttp
import random
import yt_dlp
from py_yt import VideosSearch, Playlist
from L2RMUSIC import logger, config
from L2RMUSIC.helpers import Track, utils

API_URL = os.environ.get("SHRUTI_API_URL", "https://api.shrutibots.site")

API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotsbNn7OBwod2NR0aH88nXR") ## Get This API KEY FROM TELEGRAM BOT USERNAME: @SHRUTIAPIBOT

DOWNLOAD_DIR = "downloads"


async def download_song(link: str) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
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
    except Exception:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None


async def download_video(link: str) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
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
    except Exception:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.cookie_dir = "AloneX/cookies"

    def get_cookies(self):
        if not os.path.exists(self.cookie_dir):
            return None
        cookies_files = [f for f in os.listdir(self.cookie_dir) if f.endswith(".txt")]
        if not cookies_files:
            return None
        return os.path.join(self.cookie_dir, random.choice(cookies_files))

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies from urls...")
        if not os.path.exists(self.cookie_dir):
            os.makedirs(self.cookie_dir)
        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(urls):
                path = f"{self.cookie_dir}/cookie_{i}.txt"
                link = "https://batbin.me/api/v2/paste/" + url.split("/")[-1]
                async with session.get(link) as resp:
                    resp.raise_for_status()
                    with open(path, "wb") as fw:
                        fw.write(await resp.read())
        logger.info(f"Cookies saved in {self.cookie_dir}.")

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        try:
            _search = VideosSearch(query, limit=1)
            results = await _search.next()
            if results and results["result"]:
                data = results["result"][0]
                return Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name"),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")) if data.get("duration") else 0,
                    message_id=m_id,
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                    url=data.get("link"),
                    view_count=data.get("viewCount", {}).get("short"),
                    video=video,
                )
        except Exception as e:
            logger.error(f"Search error: {e}")
        return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track]:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist.get("videos", [])[:limit]:
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")) if data.get("duration") else 0,
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                    url=data.get("link").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except Exception as e:
            logger.error(f"Playlist error: {e}")
        return tracks

    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None

        if video:
            return await download_video(video_id)
        else:
            return await download_song(video_id)

    def _format_duration(self, seconds: int) -> str:
        seconds = max(int(seconds or 0), 0)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _format_views(self, count) -> str:
        if not count:
            return ""
        count = int(count)
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M views"
        if count >= 1_000:
            return f"{count / 1_000:.1f}K views"
        return f"{count} views"

    def _extract_related(self, video_id: str) -> dict | None:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "ignoreerrors": True,
            "geo_bypass": True,
            "socket_timeout": 10,
            "retries": 1,
            "extractor_retries": 1,
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        }
        cookie = self.get_cookies()
        if cookie:
            opts["cookiefile"] = cookie

        url = f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}"
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    async def _related_from_mix(
        self, video_id: str, played: set[str]
    ) -> Track | None:
        loop = asyncio.get_event_loop()
        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, self._extract_related, video_id),
                timeout=20,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[Autoplay] Mix fetch timed out for {video_id}.")
            return None
        except Exception as e:
            logger.error(f"[Autoplay] Mix fetch failed for {video_id}: {e}")
            return None

        entries = (info or {}).get("entries") or []
        for entry in entries:
            if not entry:
                continue

            eid = entry.get("id")
            if not eid or eid in played:
                continue

            title = entry.get("title") or "Unknown"
            if title.lower() in ("[deleted video]", "[private video]"):
                continue

            duration = int(entry.get("duration") or 0)
            if duration <= 0 or duration > config.DURATION_LIMIT:
                continue

            thumbs = entry.get("thumbnails") or []
            thumbnail = thumbs[-1]["url"].split("?")[0] if thumbs else None

            return Track(
                id=eid,
                channel_name=entry.get("channel") or entry.get("uploader") or "YouTube",
                duration=self._format_duration(duration),
                duration_sec=duration,
                title=title[:25],
                thumbnail=thumbnail,
                url=f"https://www.youtube.com/watch?v={eid}",
                view_count=self._format_views(entry.get("view_count")),
                video=False,
            )

        return None

    async def _related_from_search(
        self, current: Track, played: set[str]
    ) -> Track | None:
        """Fallback used when YouTube blocks the mix-playlist scrape (common on
        server/cloud IPs without cookies). Reuses the same search backend that
        already powers /play, so it works wherever normal search works."""
        queries = []
        if current.channel_name:
            queries.append(f"{current.channel_name}")
        if current.title:
            queries.append(f"{current.title}")

        for query in queries:
            try:
                _search = VideosSearch(query, limit=8)
                results = await _search.next()
            except Exception as e:
                logger.error(f"[Autoplay] Search fallback failed for {query!r}: {e}")
                continue

            for data in (results or {}).get("result", []):
                eid = data.get("id")
                if not eid or eid in played:
                    continue

                duration_str = data.get("duration")
                duration_sec = utils.to_seconds(duration_str) if duration_str else 0
                if not duration_sec or duration_sec > config.DURATION_LIMIT:
                    continue

                return Track(
                    id=eid,
                    channel_name=data.get("channel", {}).get("name") or "YouTube",
                    duration=duration_str,
                    duration_sec=duration_sec,
                    title=(data.get("title") or "Unknown")[:25],
                    thumbnail=(data.get("thumbnails", [{}])[-1].get("url") or "").split("?")[0] or None,
                    url=data.get("link"),
                    view_count=data.get("viewCount", {}).get("short"),
                    video=False,
                )

        return None

    async def get_related(
        self, current: Track, played: list[str] | None = None
    ) -> Track | None:
        """Fetch the next autoplay track, skipping anything already played in
        this session. Tries YouTube's related mix first, falling back to a
        text search (same backend as /play) if the mix is blocked or empty —
        this is common on server/cloud IPs without YouTube cookies set."""
        if not current or not current.id:
            return None

        played = set(played or [])
        played.add(current.id)

        related = await self._related_from_mix(current.id, played)
        if related:
            return related

        logger.info(
            f"[Autoplay] Mix returned nothing for {current.id}, trying search fallback."
        )
        related = await self._related_from_search(current, played)
        if related:
            return related

        logger.warning(f"[Autoplay] No related track found for {current.id}.")
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
        if self._cache_disabled or PLAYLIST_ID is None:
            return False
        if not await self._validate_channel():
            return False
        try:
            if not os.path.exists(file_path) or os.path.getsize(file_path) < 2048:
                return False
            db_id = f"{vid_id}_video" if is_video else vid_id

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
            except Exception as e:
                logger.error(f"❌ Upload failed: {e}")
                self._cache_disabled = True
                return False

            if msg and msg.id:
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
        if self._cache_disabled or PLAYLIST_ID is None:
            return None
        if not await self._validate_channel():
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
        except Exception as e:
            logger.error(f"❌ Cache retrieval failed: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
        return None

    async def _search_cache_by_title(self, query: str) -> Optional[dict]:
        if self._cache_disabled or PLAYLIST_ID is None:
            return None
        if not await self._validate_channel():
            return None
        try:
            regex = re.compile(query, re.IGNORECASE)
            doc = await trackdb.find_one({"title": {"$regex": regex}})
            if doc:
                vid_id = doc["vid_id"].replace("_video", "").replace("_audio", "")
                duration = doc.get("duration", "0:00")
                thumb = doc.get("thumb", "")
                title = doc["title"]
                is_video = doc["type"] == "video"
                logger.info(f"✅ Found cached song: {title} (ID: {vid_id})")
                return {
                    "title": title,
                    "duration": duration,
                    "seconds": time_to_seconds(duration) if duration != "0:00" else 0,
                    "thumb": thumb,
                    "vid_id": vid_id,
                    "is_video": is_video
                }
        except Exception as e:
            logger.error(f"❌ Cache search error: {e}")
        return None

    async def get_random_cached_song(self) -> Optional[dict]:
        """Pick a random song from the cache database."""
        if self._cache_disabled or PLAYLIST_ID is None:
            return None
        if not await self._validate_channel():
            return None
        try:
            pipeline = [{"$sample": {"size": 1}}]
            cursor = trackdb.aggregate(pipeline)
            doc = await cursor.to_list(length=1)
            if doc:
                doc = doc[0]
                vid_id = doc["vid_id"].replace("_video", "").replace("_audio", "")
                duration = doc.get("duration", "0:00")
                thumb = doc.get("thumb", "")
                title = doc["title"]
                is_video = doc["type"] == "video"
                logger.info(f"🎲 Random cached song selected: {title} (ID: {vid_id})")
                return {
                    "title": title,
                    "duration": duration,
                    "seconds": time_to_seconds(duration) if duration != "0:00" else 0,
                    "thumb": thumb,
                    "vid_id": vid_id,
                    "is_video": is_video
                }
        except Exception as e:
            logger.error(f"❌ Failed to get random cached song: {e}")
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

    # ---------- YT-DLP ----------
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

    # ---------- MAIN DOWNLOAD (with automatic random fallback) ----------
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
        If all methods fail, automatically pick a random cached song.
        """
        # If videoid not given and link is not a URL, treat as search query
        if not videoid and not re.search(self.regex, link):
            cached = await self._search_cache_by_title(link)
            if cached:
                vid_id = cached["vid_id"]
                is_video_request = cached.get("is_video", False)
                filepath = await self.get_cached_file(vid_id, is_video=is_video_request)
                if filepath:
                    logger.info(f"✅ Playing from cache (title match): {filepath}")
                    return filepath, True
                else:
                    logger.warning("⚠️ Cached metadata found but file missing – re-downloading")
                    videoid = vid_id
                    title = cached["title"]
                    duration = cached.get("duration")
                    thumb = cached.get("thumb")

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
        is_cached = False

        # 1. Check cache by ID
        cached_file = await self.get_cached_file(vid_id, is_video=is_video_request)
        if cached_file:
            logger.info(f"✅ Retrieved from cache (by ID): {cached_file}")
            return cached_file, True

        # Ensure we have a proper title
        if not title or title == vid_id:
            try:
                title, dur, _, thumb_url, _ = await self.details(vid_id, videoid=vid_id)
                if not duration:
                    duration = dur
                if not thumb:
                    thumb = thumb_url
            except Exception as e:
                logger.warning(f"Could not fetch details: {e}")
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

        # 5. If still no file, fallback to a random cached song (advance logic)
        if not filepath:
            logger.warning("⚠️ All download methods failed. Falling back to random cached song.")
            random_song = await self.get_random_cached_song()
            if random_song:
                rand_vid = random_song["vid_id"]
                rand_is_video = random_song["is_video"]
                filepath = await self.get_cached_file(rand_vid, is_video=rand_is_video)
                if filepath:
                    title = random_song["title"]
                    duration = random_song.get("duration")
                    thumb = random_song.get("thumb")
                    vid_id = rand_vid
                    is_video_request = rand_is_video
                    is_cached = True
                    logger.info(f"🎲 Playing random cached song: {title} (file: {filepath})")
                else:
                    # If even random cache fails, raise error
                    raise Exception("❌ No songs available in cache and all downloads failed.")
            else:
                raise Exception("❌ No songs available in cache and all downloads failed.")

        # Background upload to cache (if not already cached)
        if not is_cached:
            asyncio.create_task(
                self._upload_to_cache(vid_id, filepath, title, is_video_request, duration, thumb)
            )

        return filepath, is_cached

    # ---------- DETAILS (with cache search) ----------
    async def details(self, link, videoid=None):
        if videoid:
            link = self.base + link
        elif not re.search(self.regex, link):
            cached = await self._search_cache_by_title(link)
            if cached:
                return (
                    cached["title"],
                    cached["duration"],
                    cached["seconds"],
                    cached["thumb"],
                    cached["vid_id"]
                )

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
