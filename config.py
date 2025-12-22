import re
from os import getenv
from dotenv import load_dotenv
from pyrogram import filters

load_dotenv()

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
# Get this value from my.telegram.org/apps
API_ID = int(getenv("API_ID", "23392712"))

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
API_HASH = getenv("API_HASH", "7cb236b197b25c243fa83e7e0173d0e6")

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
# Get your token from @BotFather on Telegram.
BOT_TOKEN = getenv("BOT_TOKEN", "")

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
# Get your MongoDB URI from cloud.mongodb.com
MONGO_DB_URI = getenv("MONGO_DB_URI", "")

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
DURATION_LIMIT_MIN = int(getenv("DURATION_LIMIT", "5400"))
SONG_DOWNLOAD_DURATION = int(getenv("SONG_DOWNLOAD_DURATION_LIMIT", "5400"))

# Chat ID of a group for logging bot's activities
LOGGER_ID = int(getenv("LOGGER_ID", "0"))

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
OWNER_ID = int(getenv("OWNER_ID", "5820831398"))

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
HEROKU_APP_NAME = getenv("HEROKU_APP_NAME", "")
HEROKU_API_KEY = getenv("HEROKU_API_KEY", "")

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
UPSTREAM_REPO = getenv("UPSTREAM_REPO", "https://github.com/BWFTIME/L2RMUSIC")
UPSTREAM_BRANCH = getenv("UPSTREAM_BRANCH", "master")
GIT_TOKEN = getenv("GIT_TOKEN", None)

API_URL = getenv("API_URL", "https://api.thequickearn.xyz")
VIDEO_API_URL = getenv("VIDEO_API_URL", "https://api.video.thequickearn.xyz")
API_KEY = getenv("YT_API_KEY", None)

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
SUPPORT_CHANNEL = getenv("SUPPORT_CHANNEL", "https://t.me/ALL_QUIZ_TAME")
SUPPORT_CHAT = getenv("SUPPORT_CHAT", "https://t.me/BWF_MUSIC1")

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
AUTO_LEAVING_ASSISTANT = getenv("AUTO_LEAVING_ASSISTANT", "False").lower() == "true"
AUTO_SUGGESTION_MODE = getenv("AUTO_SUGGESTION_MODE", "False").lower() == "true"
AUTO_SUGGESTION_TIME = int(getenv("AUTO_SUGGESTION_TIME", "5400"))

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
SPOTIFY_CLIENT_ID = getenv("SPOTIFY_CLIENT_ID", "bcfe26b0ebc3428882a0b5fb3e872473")
SPOTIFY_CLIENT_SECRET = getenv("SPOTIFY_CLIENT_SECRET", "907c6a054c214005aeae1fd752273cc4")

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
PLAYLIST_FETCH_LIMIT = int(getenv("PLAYLIST_FETCH_LIMIT", "25"))
CLEANMODE_DELETE_MINS = int(getenv("CLEANMODE_MINS", "5"))

TG_AUDIO_FILESIZE_LIMIT = int(getenv("TG_AUDIO_FILESIZE_LIMIT", "104857600"))
TG_VIDEO_FILESIZE_LIMIT = int(getenv("TG_VIDEO_FILESIZE_LIMIT", "1073741824"))

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
STRING1 = getenv("STRING_SESSION", "")
STRING2 = getenv("STRING_SESSION2", "")
STRING3 = getenv("STRING_SESSION3", "")
STRING4 = getenv("STRING_SESSION4", "")
STRING5 = getenv("STRING_SESSION5", "")

# ━━━━━━━━━━━━━❖ ➥ 𝐿2𝙍 𝗠𝗨𝗦𝗜𝗖™🇮🇳 ━━━━━━━━━━━
BANNED_USERS = filters.user()
adminlist = {}
lyrical = {}
votemode = {}
autoclean = []
confirmer = {}
chatstats = {}
userstats = {}
clean = {}

# ━━━━━━━━━━━━━❖ ➥ Default Images ━━━━━━━━━━━
DEFAULT_IMG = "https://telegra.ph/file/e576aa8308c49d945f433.jpg"
START_IMG_URL = getenv("START_IMG_URL", DEFAULT_IMG)
PING_IMG_URL = getenv("PING_IMG_URL", DEFAULT_IMG)
PLAYLIST_IMG_URL = DEFAULT_IMG
STATS_IMG_URL = DEFAULT_IMG
TELEGRAM_AUDIO_URL = DEFAULT_IMG
TELEGRAM_VIDEO_URL = DEFAULT_IMG
STREAM_IMG_URL = DEFAULT_IMG
SOUNCLOUD_IMG_URL = DEFAULT_IMG
YOUTUBE_IMG_URL = DEFAULT_IMG
SPOTIFY_ARTIST_IMG_URL = DEFAULT_IMG
SPOTIFY_ALBUM_IMG_URL = DEFAULT_IMG
SPOTIFY_PLAYLIST_IMG_URL = DEFAULT_IMG


# ━━━━━━━━━━━━━❖ ➥ Helper Function ━━━━━━━━━━━
def time_to_seconds(time: str) -> int:
    """Convert time string (HH:MM:SS or MM:SS) to total seconds."""
    parts = time.split(":")
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(parts)))


DURATION_LIMIT = time_to_seconds(f"{DURATION_LIMIT_MIN}:00")
SONG_DOWNLOAD_DURATION_LIMIT = time_to_seconds(f"{SONG_DOWNLOAD_DURATION}:00")

# ━━━━━━━━━━━━━❖ ➥ URL Validation ━━━━━━━━━━━
if SUPPORT_CHANNEL and not re.match(r"(?:http|https)://", SUPPORT_CHANNEL):
    raise SystemExit("[ERROR] - Your SUPPORT_CHANNEL URL is invalid. It must start with https://")

if SUPPORT_CHAT and not re.match(r"(?:http|https)://", SUPPORT_CHAT):
    raise SystemExit("[ERROR] - Your SUPPORT_CHAT URL is invalid. It must start with https://")
