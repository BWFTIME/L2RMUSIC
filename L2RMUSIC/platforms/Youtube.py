import asyncio
import os
import re
from typing import Union, Tuple, Optional
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from py_yt import VideosSearch, Playlist
import aiohttp
from pyrogram import Client  # मान लिया गया

# ---------- आपकी मौजूदा सेटिंग्स ----------
API_URL = os.environ.get("SHRUTI_API_URL", "https://api.shrutibots.site")
API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotsOXrRk6qV3cgPptroKV1y")
DOWNLOAD_DIR = "downloads"

# ---------- नया: चैनल ID ----------
CHANNEL_ID = -1003616869403  # आपका चैनल

# ---------- नया: वैश्विक कैश (video_id → file_id) ----------
# इसे डेटाबेस में बदल सकते हैं ताकि रीस्टार्ट पर भी बना रहे
CACHE = {}

# ---------- Pyrogram क्लाइंट (आपकी मुख्य app) ----------
# मान लिया गया कि आपने app = Client(...) बनाया है
# यदि नाम अलग है तो नीचे सभी जगह बदल दें
app = Client("my_bot")   # <-- अपने वास्तविक नाम से बदलें

# ---------- यूटिलिटी फंक्शन ----------
def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))

# ---------- नया: चैनल पर अपलोड करने का फंक्शन ----------
async def upload_to_channel(file_path: str, is_audio: bool = True) -> Optional[str]:
    """
    फ़ाइल को चैनल पर भेजता है और audio/video का file_id लौटाता है।
    अगर फ़ाइल पहले से चैनल पर है (CACHE से), तो file_id लौटा देता है।
    """
    # फ़ाइल का नाम (video_id) निकालें
    base = os.path.basename(file_path)
    video_id = os.path.splitext(base)[0]  # मान लिया गया कि फ़ाइल का नाम video_id है

    # पहले कैश देखें
    if video_id in CACHE:
        return CACHE[video_id]

    try:
        if is_audio:
            msg = await app.send_audio(
                chat_id=CHANNEL_ID,
                audio=file_path,
                caption=f"🎵 {base}"
            )
            file_id = msg.audio.file_id
        else:
            msg = await app.send_video(
                chat_id=CHANNEL_ID,
                video=file_path,
                caption=f"🎬 {base}"
            )
            file_id = msg.video.file_id

        # कैश में सेव करें
        CACHE[video_id] = file_id
        return file_id
    except Exception as e:
        print(f"Upload error: {e}")
        return None

# ---------- डाउनलोड फंक्शन (अपडेटेड) ----------
async def download_song(link: str) -> Tuple[Optional[str], Optional[str], bool]:
    """
    गाना डाउनलोड करता है, चैनल पर अपलोड करता है,
    और (local_path, file_id, success) लौटाता है।
    """
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None, None, False

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")

    # अगर लोकल फ़ाइल पहले से है, तो उसे अपलोड करें (यदि पहले नहीं किया)
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        file_id = await upload_to_channel(file_path, is_audio=True)
        return file_path, file_id, True

    # डाउनलोड करें
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/download",
                params={"url": video_id, "type": "audio", "api_key": API_KEY},
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                if resp.status != 200:
                    return None, None, False
                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            # अब चैनल पर अपलोड करें
            file_id = await upload_to_channel(file_path, is_audio=True)
            return file_path, file_id, True
        return None, None, False
    except Exception:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None, None, False


async def download_video(link: str) -> Tuple[Optional[str], Optional[str], bool]:
    """वीडियो डाउनलोड + चैनल अपलोड, (local_path, file_id, success)"""
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None, None, False

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        file_id = await upload_to_channel(file_path, is_audio=False)
        return file_path, file_id, True

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/download",
                params={"url": video_id, "type": "video", "api_key": API_KEY},
                timeout=aiohttp.ClientTimeout(total=600)
            ) as resp:
                if resp.status != 200:
                    return None, None, False
                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            file_id = await upload_to_channel(file_path, is_audio=False)
            return file_path, file_id, True
        return None, None, False
    except Exception:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None, None, False


# ---------- YouTubeAPI क्लास (संशोधित) ----------
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

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

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result["id"]
            duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["title"]

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["duration"]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["thumbnails"][0]["url"].split("?")[0]

    # ----- संशोधित: video() अब upload भी करता है -----
    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            local_path, file_id, success = await download_video(link)
            if success:
                # file_id या local_path में से कोई एक वापस करें
                return 1, (local_path, file_id)
            return 0, "Video download/upload failed"
        except Exception as e:
            return 0, f"Video error: {e}"

    # ----- संशोधित: download() अब upload भी करता है -----
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
    ) -> Tuple[Optional[str], bool]:
        if videoid:
            link = self.base + link
        try:
            if video:
                local_path, file_id, success = await download_video(link)
            else:
                local_path, file_id, success = await download_song(link)
            if success:
                # file_id (या local_path) लौटाएँ
                return (local_path, file_id), True
            return None, False
        except Exception:
            return None, False

    # अन्य मेथड (playlist, track, formats, slider) यथावत रहेंगे
    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            plist = await Playlist.get(link)
        except Exception:
            return []
        videos = plist.get("videos") or []
        ids = []
        for data in videos[:limit]:
            if not data:
                continue
            vid = data.get("id")
            if not vid:
                continue
            ids.append(vid)
        return ids

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            vidid = result["id"]
            yturl = result["link"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        track_details = {
            "title": title,
            "link": yturl,
            "vidid": vidid,
            "duration_min": duration_min,
            "thumb": thumbnail,
        }
        return track_details, vidid

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        ytdl_opts = {"quiet": True}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for format in r["formats"]:
                try:
                    if "dash" not in str(format["format"]).lower():
                        formats_available.append(
                            {
                                "format": format["format"],
                                "filesize": format.get("filesize"),
                                "format_id": format["format_id"],
                                "ext": format["ext"],
                                "format_note": format["format_note"],
                                "yturl": link,
                            }
                        )
                except Exception:
                    continue
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        a = VideosSearch(link, limit=10)
        result = (await a.next()).get("result")
        title = result[query_type]["title"]
        duration_min = result[query_type]["duration"]
        vidid = result[query_type]["id"]
        thumbnail = result[query_type]["thumbnails"][0]["url"].split("?")[0]
        return title, duration_min, thumbnail, vidid


YouTube = YouTubeAPI()


# ---------- उदाहरण: /play कमांड हैंडलर (आपके बॉट में डालें) ----------
# यह मान कर चल रहा हूँ कि आपने @Client.on_message() डेकोरेटर लगाया है
# और आपके पास voice chat स्ट्रीम करने का फंक्शन है (जैसे pytgcalls)
# यहाँ केवल लॉजिक दिखा रहा हूँ:

async def play_command_handler(client, message):
    # 1. URL निकालें
    url = await YouTube.url(message)
    if not url:
        await message.reply("कोई YouTube लिंक नहीं मिला।")
        return

    # 2. video_id निकालें
    video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url

    # 3. कैश या चैनल पर पहले से अपलोड है?
    if video_id in CACHE:
        file_id = CACHE[video_id]
        # चैनल से file_id डाउनलोड करें (या सीधे स्ट्रीम करें यदि आपका प्लेयर file_id सपोर्ट करता है)
        # मान लिया कि आपको local path चाहिए:
        temp_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
        if not os.path.exists(temp_path):
            # file_id से डाउनलोड करें
            await client.download_media(file_id, file_name=temp_path)
        # अब temp_path पर गाना चलाएँ
        await stream_audio(temp_path)  # आपका स्ट्रीम फंक्शन
        await message.reply(f"🎶 चैनल से प्ले कर रहा हूँ: {video_id}")
        return

    # 4. नहीं तो डाउनलोड करें (अपलोड अपने आप हो जाएगा)
    local_path, file_id, success = await download_song(url)
    if success:
        # अब local_path पर गाना चलाएँ
        await stream_audio(local_path)
        await message.reply(f"✅ डाउनलोड कर चैनल पर अपलोड किया, अब प्ले कर रहा हूँ।")
    else:
        await message.reply("❌ डाउनलोड/अपलोड विफल, कृपया बाद में प्रयास करें।")

# ---------- महत्वपूर्ण: बॉट को चैनल में एडमिन/पोस्ट करने की अनुमति दें ----------
# CHANNEL_ID (-1003616869403) पर बॉट को मैसेज भेजने का अधिकार होना चाहिए।
# अगर चैनल प्राइवेट है, तो बॉट को सब्सक्राइबर/एडमिन बनाएँ।
