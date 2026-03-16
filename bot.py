import os
import time
import subprocess
import asyncio
import psutil

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = 30291360
API_HASH = "0f7c28c9e4c3ae162d8f23e020d613b5"
BOT_TOKEN = "8796804309:AAEuZ31sWkY8XMJF5ogORBDYC3fw5xK0nYE"

ALLOWED_USERS = [6050411363, 1723943834]

DOWNLOAD_DIR = "files"
MAX_SPLIT_SIZE = "1900m"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Client(
    "dynamic_archiver",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

sessions = {}


# ---------- UTILITIES ----------

def progress_bar(p):
    filled = int(p / 10)
    return "█" * filled + "░" * (10 - filled)


def disk_status():
    usage = psutil.disk_usage("/")
    percent = usage.percent
    return percent


def ram_status():
    ram = psutil.virtual_memory().percent
    return ram


def cleanup():
    for f in os.listdir(DOWNLOAD_DIR):
        try:
            os.remove(os.path.join(DOWNLOAD_DIR, f))
        except:
            pass


cleanup()


async def render_progress(msg, stage, percent, speed=0, eta=0):

    text = f"""
╭━━━ Dynamic Archiver ━━━╮

⚡ Stage : {stage}

{progress_bar(percent)} {percent:.1f}%

🚀 Speed : {speed:.2f} MB/s
⏳ ETA   : {eta}s
💾 Disk  : {disk_status()}%
🧠 RAM   : {ram_status()}%

╰━━━━━━━━━━━━━━━━━━━━━━━╯
"""

    try:
        await msg.edit(text)
    except:
        pass


async def upload_with_retry(message, file_path):

    for attempt in range(3):

        try:
            await message.reply_document(file_path)
            return True

        except Exception:

            await asyncio.sleep(3)

    return False


# ---------- BOT COMMANDS ----------

@app.on_message(filters.command("start"))
async def start(_, m):

    if m.from_user.id not in ALLOWED_USERS:
        return

    sessions[m.from_user.id] = {
        "files": [],
        "format": None,
        "level": None,
        "name": None,
        "password": None
    }

    await m.reply("📦 Dynamic Archiver\nUpload files then send /done")


@app.on_message(filters.document | filters.video | filters.audio)
async def collect(_, m):

    user = m.from_user.id

    if user not in sessions:
        return

    sessions[user]["files"].append(m)

    await m.reply("📁 File added")


@app.on_message(filters.command("done"))
async def choose_format(_, m):

    user = m.from_user.id

    if not sessions[user]["files"]:
        await m.reply("Upload files first.")
        return

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ZIP", callback_data="fmt_zip"),
            InlineKeyboardButton("7Z", callback_data="fmt_7z")
        ]
    ])

    await m.reply("Choose format", reply_markup=kb)


@app.on_callback_query(filters.regex("fmt_"))
async def choose_level(_, q):

    user = q.from_user.id
    sessions[user]["format"] = q.data.split("_")[1]

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Low", callback_data="lvl_low"),
            InlineKeyboardButton("Medium", callback_data="lvl_med"),
            InlineKeyboardButton("High", callback_data="lvl_high")
        ]
    ])

    await q.message.edit("Compression level", reply_markup=kb)


@app.on_callback_query(filters.regex("lvl_"))
async def ask_name(_, q):

    user = q.from_user.id
    sessions[user]["level"] = q.data.split("_")[1]

    await q.message.edit(
        "Send archive name\n\nExample:\narchive | password"
    )


@app.on_message(filters.text)
async def process(_, m):

    user = m.from_user.id

    if user not in sessions:
        return

    if sessions[user]["name"] is None:

        txt = m.text.split("|")

        sessions[user]["name"] = txt[0].strip()

        if len(txt) > 1:
            sessions[user]["password"] = txt[1].strip()

        status = await m.reply("Downloading files...")

        paths = []

        start = time.time()

        try:

            for msg in sessions[user]["files"]:

                name = msg.document.file_name.replace("/", "_")
                path = os.path.join(DOWNLOAD_DIR, name)

                await msg.download(file_name=path)
                
                paths.append(path)

            await status.edit("⚡ Compressing...")

            level_map = {"low": "1", "med": "5", "high": "9"}
            level = level_map[sessions[user]["level"]]

            name = sessions[user]["name"]
            password = sessions[user]["password"]

            archive = os.path.join(DOWNLOAD_DIR, name)

            cmd = [
                "7z",
                "a",
                "-mmt=on",
                "-m0=lzma2",
                f"-mx={level}",
                f"-v{MAX_SPLIT_SIZE}"
            ]

            if password:
                cmd.append(f"-p{password}")

            if sessions[user]["format"] == "zip":
                cmd.append("-tzip")
            else:
                cmd.append("-t7z")

            cmd.append(archive)
            cmd += paths

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            percent = 0

            while process.poll() is None:

                percent += 1
                if percent > 100:
                    percent = 100

                await render_progress(status, "Compressing", percent)

                await asyncio.sleep(1)

            await status.edit("Uploading archive...")

            parts = [
                os.path.join(DOWNLOAD_DIR, f)
                for f in os.listdir(DOWNLOAD_DIR)
                if f.startswith(name)
            ]

            for p in parts:

                await upload_with_retry(m, p)

            await status.edit("✅ Archive complete!")

            cleanup()

            sessions.pop(user)

        except Exception as e:

            await status.edit(f"❌ Error:\n{e}")

            cleanup()

            sessions.pop(user, None)


print("Dynamic Archiver Titan+ Running")
app.run()
