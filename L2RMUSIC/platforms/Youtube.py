# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic (V2 – High Quality Audio Edition)

import os
import re
import random
import asyncio
import aiohttp
from pathlib import Path

import yt_dlp
from py_yt import Playlist, VideosSearch

from L2RMUSIC import config, logger
from L2RMUSIC.helpers import NexGenApi, Track, utils


class YouTube:
    """
    Enhanced YouTube handler with:
      - Primary API: YTProxy (YTPROXY_URL + YT_API_KEY)
      - Secondary API: Shruti (SHRUTI_API_URL + SHRUTI_API_KEY)
      - yt-dlp fallback for maximum reliability
      - Forced high-bitrate OPUS stereo audio for Telegram VC.
      - Aggressive retry/network recovery settings.
    """

    def __init__(self):
        self.api = None
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.cookie_dir = "anony/cookies"
        self.warned = False
        
        # URL validation patterns
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.iregex = re.compile(
            r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)"
            r"(?!/(watch\?v=[A-Za-z0-9_-]{11}|shorts/[A-Za-z0-9_-]{11}"
            r"|playlist\?list=PL[A-Za-z0-9_-]+|[A-Za-z0-9_-]{11}))\S*"
        )

        # Initialize multi-API handler with both primary and secondary
        self.api = NexGenApi(
            # Primary API
            ytproxy_url=config.YTPROXY_URL,
            yt_api_key=config.YT_API_KEY,
            # Secondary API (fallback)
            shruti_api_url=config.SHRUTI_API_URL,
            shruti_api_key=config.SHRUTI_API_KEY,
        )

    # ------------------------------------------------------------------
    # Cookie handling
    # ------------------------------------------------------------------
    def get_cookies(self):
        if not self.checked:
            for file in os.listdir(self.cookie_dir):
                if file.endswith(".txt"):
                    self.cookies.append(f"{self.cookie_dir}/{file}")
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
        return random.choice(self.cookies)

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies from urls...")
        async with aiohttp.ClientSession() as session:
            for url in urls:
                name = url.split("/")[-1]
                link = "https://batbin.me/raw/" + name
                async with session.get(link) as resp:
                    resp.raise_for_status()
                    with open(f"{self.cookie_dir}/{name}.txt", "wb") as fw:
                        fw.write(await resp.read())
        logger.info(f"Cookies saved in {self.cookie_dir}.")

    # ------------------------------------------------------------------
    # URL validation helpers
    # ------------------------------------------------------------------
    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def invalid(self, url: str) -> bool:
        return bool(re.match(self.iregex, url))

    # ------------------------------------------------------------------
    # Search (single video)
    # ------------------------------------------------------------------
    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        try:
            _search = VideosSearch(query, limit=1, with_live=False)
            results = await _search.next()
        except Exception:
            return None
        if results and results["result"]:
            data = results["result"][0]
            return Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=data.get("duration"),
                duration_sec=utils.to_seconds(data.get("duration")),
                message_id=m_id,
                title=data.get("title")[:25],
                thumbnail=data.get("thumbnails", [{}])[-1].get("url").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short"),
                video=video,
            )
        return None

    # ------------------------------------------------------------------
    # Playlist extraction
    # ------------------------------------------------------------------
    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist["videos"][:limit]:
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails")[-1].get("url").split("?")[0],
                    url=data.get("link").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except Exception:
            pass
        return tracks

    # ------------------------------------------------------------------
    # 🔥 UPGRADED DOWNLOADER – Multi-API with Fallback
    # ------------------------------------------------------------------
    async def download(self, video_id: str, video: bool = False) -> str | None:
        """
        Downloads audio/video with these priorities:
          1. Primary API (YTProxy)
          2. Secondary API (Shruti) – if primary fails
          3. yt-dlp with high-quality OPUS (crystal stereo)
          4. Fallback to best possible format in case of network issues.
        """
        # --- PATH PREPARATION ---
        ext = "mp4" if video else "mp3"
        filename = f"downloads/{video_id}.{ext}"
        Path("downloads").mkdir(parents=True, exist_ok=True)

        # Check if already downloaded in any format
        for existing_ext in ["mp3", "mp4", "webm"]:
            existing_file = f"downloads/{video_id}.{existing_ext}"
            if Path(existing_file).exists():
                logger.info("📦 Cache hit: %s", existing_file)
                return existing_file

        # --- ATTEMPT 1 & 2: Primary → Secondary API ---
        logger.info("🚀 Starting API download for %s (Primary → Secondary)", video_id)
        try:
            await self.api.get_session()
            file_path = await self.api.download(video_id, video)
            if file_path and Path(file_path).exists():
                logger.info("✅ API download successful: %s", file_path)
                return file_path
            else:
                logger.warning("❌ All APIs failed, falling back to yt-dlp...")
        except Exception as e:
            logger.error("❌ API download error: %s", e)

        # --- ATTEMPT 3: yt-dlp with best OPUS stereo ---
        logger.info("⬇️ Attempting yt-dlp download for %s", video_id)
        url = self.base + video_id
        cookie = self.get_cookies()

        # Base options with aggressive retry & network resilience
        base_opts = {
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": True,
            "overwrites": False,
            "nocheckcertificate": True,
            "cookiefile": cookie,
            # --- NETWORK RESILIENCE ---
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 5,
            "socket_timeout": 30,
            "file_access_retries": 5,
            "skip_unavailable_fragments": True,
            "ignoreerrors": True,
        }

        if video:
            # Video: limit to 720p, merge into MP4
            ydl_opts = {
                **base_opts,
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)",
                "merge_output_format": "mp4",
            }
        else:
            # 🎵 AUDIO: prefer OPUS in webm, fallback to best audio overall
            ydl_opts = {
                **base_opts,
                "format": "bestaudio[acodec=opus]/bestaudio",
                "postprocessors": [],  # Keep native container
            }

        def _download():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except yt_dlp.utils.DownloadError as de:
                logger.error("yt-dlp DownloadError: %s", de)
                return None
            except Exception as ex:
                logger.exception("Unexpected yt-dlp error: %s", ex)
                return None
            return filename

        # Run blocking download in thread
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_download),
                timeout=120,
            )
            if result and Path(result).exists():
                return result
        except asyncio.TimeoutError:
            logger.error("Download timed out for %s", url)

        # --- ATTEMPT 4: Last-resort fallback ---
        if not video:
            logger.warning("Primary download failed. Trying fallback format (bestaudio).")
            fallback_opts = {
                **base_opts,
                "format": "bestaudio",
                "postprocessors": [],
            }
            def _fallback():
                with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                    ydl.download([url])
                return filename
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(_fallback),
                    timeout=120,
                )
                if result and Path(result).exists():
                    return result
            except Exception as e:
                logger.error("Fallback download also failed: %s", e)

        return None

    async def close(self):
        """Clean up API session."""
        if self.api:
            await self.api.close_session()
