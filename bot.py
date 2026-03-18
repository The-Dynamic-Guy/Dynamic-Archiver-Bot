import os
import time
import zipfile
import asyncio
import shutil

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

DOWNLOAD_DIR = "files"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Client("dynamic_archiver", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

sessions = {}

def progress_bar(p):
    filled = int(p / 10)
    return "█" * filled + "░" * (10 - filled)

async def progress(current, total, msg, stage, start):
    percent = current * 100 / total if total else 0
    elapsed = time.time() - start
    speed = current / elapsed if elapsed else 0
    eta = (total - current) / speed if speed else 0

    text = f"""
📦 Dynamic Archiver

Stage: {stage}
{progress_bar(percent)} {percent:.1f}%

Speed: {speed/1024/1024:.2f} MB/s
ETA: {int(eta)}s
"""

    try:
        await msg.edit(text)
    except:
        pass

@app.on_message(filters.command("start"))
async def start(_, m):
    sessions[m.from_user.id] = {
        "files": [],
        "format": None,
        "level": None,
        "name": None
    }
    await m.reply("📦 Dynamic Archiver\nUpload files then send /done")

@app.on_message(filters.document)
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
        [InlineKeyboardButton("ZIP", callback_data="zip")]
    ])
    await m.reply("Choose format", reply_markup=kb)

@app.on_callback_query(filters.regex("zip"))
async def ask_name(_, q):
    sessions[q.from_user.id]["format"] = "zip"
    await q.message.edit("Send archive name")

@app.on_message(filters.text & ~filters.command(["start", "done"]))
async def process(_, m):
    user = m.from_user.id

    if user not in sessions:
        return

    if sessions[user]["name"] is None:
        sessions[user]["name"] = m.text.strip()

        status = await m.reply("Downloading...")

        paths = []
        start = time.time()

        for msg in sessions[user]["files"]:
            name = msg.document.file_name.replace("/", "_")
            path = os.path.join(DOWNLOAD_DIR, name)

            await msg.download(
                file_name=path,
                progress=progress,
                progress_args=(status, "Downloading", start)
            )

            paths.append(path)

        await status.edit("⚡ Compressing...")

        archive_path = os.path.join(DOWNLOAD_DIR, sessions[user]["name"] + ".zip")

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in paths:
                z.write(p, os.path.basename(p))

        await status.edit("Uploading...")

        await m.reply_document(
            archive_path,
            progress=progress,
            progress_args=(status, "Uploading", start)
        )

        await status.edit("✅ Done!")

        for p in paths:
            os.remove(p)

        os.remove(archive_path)
        sessions.pop(user)

print("Bot running...")
app.run()
