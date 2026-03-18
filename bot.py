import os
import time
import zipfile

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

DOWNLOAD_DIR = "files"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Client("dynamic_archiver", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

sessions = {}

# ---------- UI ----------

def progress_bar(p):
    filled = int(p / 10)
    return "█" * filled + "░" * (10 - filled)


async def progress(current, total, msg, stage, start, files=1):
    percent = current * 100 / total if total else 0
    elapsed = time.time() - start
    speed = current / elapsed if elapsed else 0
    eta = (total - current) / speed if speed else 0

    text = f"""
╭━━━ Dynamic Archiver ━━━╮

⚡ Stage: {stage}
📦 Files: {files}

{progress_bar(percent)} {percent:.1f}%

🚀 Speed: {speed/1024/1024:.2f} MB/s
⏳ ETA: {int(eta)}s

╰━━━━━━━━━━━━━━━━━━━━━━━╯
"""
    try:
        await msg.edit(text)
    except:
        pass


# ---------- COMMANDS ----------

@app.on_message(filters.command("start"))
async def start(_, m):
    sessions[m.from_user.id] = {
        "files": [],
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

    name = m.document.file_name
    await m.reply(f"📁 Added: {name}")


@app.on_message(filters.command("done"))
async def choose_level(_, m):
    user = m.from_user.id

    if not sessions[user]["files"]:
        await m.reply("Upload files first.")
        return

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Low ⚡", callback_data="low"),
            InlineKeyboardButton("Medium ⚖", callback_data="med"),
            InlineKeyboardButton("High 🗜", callback_data="high")
        ]
    ])

    await m.reply("Select compression level:", reply_markup=kb)


@app.on_callback_query()
async def set_level(_, q):
    user = q.from_user.id
    sessions[user]["level"] = q.data

    await q.message.edit("Send archive name")


@app.on_message(filters.text & ~filters.command(["start", "done"]))
async def process(_, m):
    user = m.from_user.id

    if user not in sessions:
        return

    if sessions[user]["name"] is None:

        sessions[user]["name"] = m.text.strip()

        status = await m.reply("Preparing...")

        start = time.time()
        paths = []
        total_files = len(sessions[user]["files"])

        # ---------- DOWNLOAD ----------
        for i, msg in enumerate(sessions[user]["files"], 1):
            name = msg.document.file_name.replace("/", "_")
            path = os.path.join(DOWNLOAD_DIR, name)

            await msg.download(
                file_name=path,
                progress=progress,
                progress_args=(status, f"Downloading ({i}/{total_files})", start, total_files)
            )

            paths.append(path)

        # ---------- COMPRESSION ----------
        await status.edit("⚡ Compressing...")

        archive = os.path.join(DOWNLOAD_DIR, sessions[user]["name"] + ".zip")

        level = sessions[user]["level"]

        compression_map = {
            "low": zipfile.ZIP_STORED,
            "med": zipfile.ZIP_DEFLATED,
            "high": zipfile.ZIP_LZMA
        }

        comp = compression_map[level]

        with zipfile.ZipFile(archive, "w", compression=comp) as z:
            for i, p in enumerate(paths, 1):
                z.write(p, os.path.basename(p))

                percent = i * 100 / total_files
                await progress(i, total_files, status, "Compressing", start, total_files)

        # ---------- UPLOAD ----------
        await status.edit("📤 Uploading...")

        await m.reply_document(
            archive,
            progress=progress,
            progress_args=(status, "Uploading", start, total_files)
        )
        
        await status.edit("✅ Done!")

        # ---------- CLEANUP ----------
        for p in paths:
            os.remove(p)

        os.remove(archive)
        sessions.pop(user)


print("Titan V2 Running 🚀")
app.run()
