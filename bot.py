import os
import time
import asyncio
import subprocess
import shutil

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

DOWNLOAD_DIR = "files"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Client("dynamic_archiver", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

sessions = {}


# ---------- CLEANUP ----------
def cleanup():
    for f in os.listdir(DOWNLOAD_DIR):
        try:
            path = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree(path)
        except:
            pass


# ---------- UI ----------
def bar(p):
    return "█" * int(p/10) + "░" * (10-int(p/10))


async def update(msg, stage, percent):
    text = f"""
╭━━━ Dynamic Archiver ━━━╮

⚡ {stage}

{bar(percent)} {percent}%

╰━━━━━━━━━━━━━━━━━━━━━━━╯
"""
    try:
        await msg.edit(text)
    except:
        pass


# ---------- START ----------
@app.on_message(filters.command("start"))
async def start(_, m):
    cleanup()

    sessions[m.from_user.id] = {
        "files": [],
        "level": None,
        "name": None
    }

    await m.reply("📦 Send files then /done")


# ---------- COLLECT ----------
@app.on_message(filters.document)
async def collect(_, m):
    if m.from_user.id not in sessions:
        return

    sessions[m.from_user.id]["files"].append(m)
    await m.reply("📁 Added")


# ---------- DONE ----------
@app.on_message(filters.command("done"))
async def done(_, m):
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Fast ⚡", callback_data="1"),
            InlineKeyboardButton("Balanced ⚖", callback_data="5"),
            InlineKeyboardButton("Ultra 🗜", callback_data="9")
        ]
    ])
    await m.reply("Select compression:", reply_markup=kb)


# ---------- LEVEL ----------
@app.on_callback_query()
async def level(_, q):
    sessions[q.from_user.id]["level"] = q.data
    await q.message.edit("Send archive name")


# ---------- PROCESS ----------
@app.on_message(filters.text & ~filters.command(["start", "done"]))
async def process(_, m):
    user = m.from_user.id

    if user not in sessions:
        return

    sessions[user]["name"] = m.text.strip()

    status = await m.reply("Preparing...")

    paths = []

    # DOWNLOAD
    for i, msg in enumerate(sessions[user]["files"], 1):
        name = msg.document.file_name.replace("/", "_")
        path = os.path.join(DOWNLOAD_DIR, name)

        await msg.download(file_name=path)
        paths.append(path)

    await status.edit("⚡ Compressing...")

    archive = os.path.join(DOWNLOAD_DIR, sessions[user]["name"])

    cmd = [
        "7z",
        "a",
        "-tzip",
        f"-mx={sessions[user]['level']}",
        archive
    ] + paths

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    percent = 0

    while process.poll() is None:
        percent = min(percent + 2, 100)
        await update(status, "Compressing", percent)
        await asyncio.sleep(1)

    await status.edit("📤 Uploading...")

    await m.reply_document(archive + ".zip")

    await status.edit("✅ Done")

    cleanup()
    sessions.pop(user)


print("Titan Pro Running 🚀")
app.run()
