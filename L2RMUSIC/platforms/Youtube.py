# FIX BY SHONA @THECDERQUEEN
import os
import re
import asyncio
import aiohttp
import random
import yt_dlp
from L2RMUSIC import logger, config
from L2RMUSIC.helpers import Track, utils

API_URL = os.environ.get("SHRUTI_API_URL", "https://api.shrutibots.site")
API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotsbNn7OBwod2NR0aH88nXR")  # Get from @SHRUTIAPIBOT
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

    # ------------------------------------------------------------
    #  Helper to run yt-dlp in a thread (async-friendly)
    # ------------------------------------------------------------
    async def _run_ydl(self, ydl_opts: dict, url: str) -> dict:
        loop = asyncio.get_event_loop()
        cookie = self.get_cookies()
        if cookie:
            ydl_opts["cookiefile"] = cookie
        return await loop.run_in_executor(
            None,
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False)
        )

    # ------------------------------------------------------------
    #  SEARCH – uses ytsearch: prefix with yt-dlp (no py_yt)
    # ------------------------------------------------------------
    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        try:
            # Use yt-dlp's built-in search extractor
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
            info = await self._run_ydl(opts, f"ytsearch1:{query}")
            entries = info.get("entries", [])
            if not entries:
                return None

            data = entries[0]
            if not data:
                return None

            # Build Track object from yt-dlp flat data
            track = Track(
                id=data.get("id"),
                channel_name=data.get("channel") or data.get("uploader") or "YouTube",
                duration=data.get("duration"),
                duration_sec=utils.to_seconds(data.get("duration")) if data.get("duration") else 0,
                message_id=m_id,
                title=(data.get("title") or "Unknown")[:25],
                thumbnail=data.get("thumbnail"),
                url=data.get("webpage_url") or f"https://www.youtube.com/watch?v={data.get('id')}",
                view_count=data.get("view_count"),
                video=video,
            )
            return track

        except Exception as e:
            logger.error(f"Search error: {e}")
        return None

    # ------------------------------------------------------------
    #  PLAYLIST – uses yt-dlp directly (no py_yt)
    # ------------------------------------------------------------
    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track]:
        tracks = []
        try:
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
            info = await self._run_ydl(opts, url)
            entries = info.get("entries", [])[:limit]
            for entry in entries:
                if not entry:
                    continue
                track = Track(
                    id=entry.get("id"),
                    channel_name=entry.get("channel") or entry.get("uploader") or "YouTube",
                    duration=entry.get("duration"),
                    duration_sec=utils.to_seconds(entry.get("duration")) if entry.get("duration") else 0,
                    title=(entry.get("title") or "Unknown")[:25],
                    thumbnail=entry.get("thumbnail"),
                    url=entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
                    user=user,
                    view_count=entry.get("view_count"),
                    video=video,
                )
                tracks.append(track)
        except Exception as e:
            logger.error(f"Playlist error: {e}")
        return tracks

    # ------------------------------------------------------------
    #  DOWNLOAD – unchanged (uses external API)
    # ------------------------------------------------------------
    async def download(self, video_id: str, video: bool = False) -> str | None:
        if not video_id or len(video_id) < 3:
            return None
        if video:
            return await download_video(video_id)
        else:
            return await download_song(video_id)

    # ------------------------------------------------------------
    #  Helpers for formatting (unchanged)
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    #  RELATED – uses yt-dlp mix + fallback search (unchanged)
    # ------------------------------------------------------------
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

    async def _related_from_mix(self, video_id: str, played: set[str]) -> Track | None:
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

    async def _related_from_search(self, current: Track, played: set[str]) -> Track | None:
        """Fallback using the same search backend (now yt-dlp)."""
        queries = []
        if current.channel_name:
            queries.append(f"{current.channel_name}")
        if current.title:
            queries.append(f"{current.title}")

        for query in queries:
            try:
                # Use the same search method (which uses yt-dlp)
                track = await self.search(query, m_id=0, video=False)
                if track and track.id not in played:
                    # re‑set the message_id to 0 (irrelevant for autoplay)
                    track.message_id = 0
                    return track
            except Exception as e:
                logger.error(f"[Autoplay] Search fallback failed for {query!r}: {e}")
                continue
        return None

    async def get_related(self, current: Track, played: list[str] | None = None) -> Track | None:
        if not current or not current.id:
            return None

        played = set(played or [])
        played.add(current.id)

        related = await self._related_from_mix(current.id, played)
        if related:
            return related

        logger.info(f"[Autoplay] Mix returned nothing for {current.id}, trying search fallback.")
        related = await self._related_from_search(current, played)
        if related:
            return related

        logger.warning(f"[Autoplay] No related track found for {current.id}.")
        return None
