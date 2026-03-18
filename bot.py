import os
import time
import zipfile
import asyncio
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


async def update(msg, stage, percent, speed=0, eta=0):
    text = f"""
╭━━━ Dynamic Archiver ━━━╮

⚡ {stage}

{bar(percent)} {percent:.1f}%

🚀 {speed:.2f} MB/s | ⏳ {int(eta)}s

╰━━━━━━━━━━━━━━━━━━━━━━━╯
"""
    try:
        await msg.edit(text)
    except:
        pass


async def progress(current, total, msg, stage, start):
    percent = current * 100 / total if total else 0
    elapsed = time.time() - start
    speed = current / elapsed if elapsed else 0
    eta = (total - current) / speed if speed else 0

    await update(msg, stage, percent, speed/1024/1024, eta)


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
            InlineKeyboardButton("Fast ⚡", callback_data="low"),
            InlineKeyboardButton("Balanced ⚖", callback_data="med"),
            InlineKeyboardButton("Ultra 🗜", callback_data="high")
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
    start = time.time()

    try:
        # ---------- DOWNLOAD ----------
        for i, msg in enumerate(sessions[user]["files"], 1):
            name = msg.document.file_name.replace("/", "_")
            path = os.path.join(DOWNLOAD_DIR, name)

            await msg.download(
                file_name=path,
                progress=progress,
                progress_args=(status, f"Downloading {i}", start)
            )

            paths.append(path)

        # ---------- COMPRESSION ----------
        await status.edit("⚡ Compressing...")

        archive = os.path.join(DOWNLOAD_DIR, sessions[user]["name"] + ".zip")

        compression_map = {
            "low": zipfile.ZIP_STORED,
            "med": zipfile.ZIP_DEFLATED,
            "high": zipfile.ZIP_LZMA
        }

        comp = compression_map[sessions[user]["level"]]

        total = len(paths)

        with zipfile.ZipFile(archive, "w", compression=comp) as z:
            for i, p in enumerate(paths, 1):
                z.write(p, os.path.basename(p))

                percent = i * 100 / total
                await update(status, "Compressing", percent)

                await asyncio.sleep(0)

        # ---------- UPLOAD ----------
        await status.edit("📤 Uploading...")
        
        await m.reply_document(
            archive,
            progress=progress,
            progress_args=(status, "Uploading", start)
        )

        await status.edit("✅ Done")

    except Exception as e:
        await status.edit(f"❌ Error: {e}")

    finally:
        cleanup()
        sessions.pop(user, None)
        
        @app.on_message(filters.command("clean"))
async def manual_clean(_, m):
    for f in os.listdir(DOWNLOAD_DIR):
        try:
            path = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree(path)
        except:
            pass

    await m.reply("🧹 Storage cleaned successfully!")


print("Titan Stable Running 🚀")
app.run()

