import os
import time
import zipfile
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = 30291360
API_HASH = "0f7c28c9e4c3ae162d8f23e020d613b5"
BOT_TOKEN = "8796804309:AAEuZ31sWkY8XMJF5ogORBDYC3fw5xK0nYE"

ALLOWED_USERS = [6050411363, 1723943834]

DOWNLOAD_DIR = "files"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Client(
    "dynamic_archiver",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

sessions = {}


def progress_bar(percent):
    filled = int(percent / 10)
    return "█" * filled + "░" * (10 - filled)


async def progress(current, total, msg, stage, start):

    percent = current * 100 / total
    elapsed = time.time() - start
    speed = current / elapsed if elapsed else 0
    eta = (total - current) / speed if speed else 0

    text = f"""
📦 Dynamic Archiver

Stage: {stage}
Progress: {progress_bar(percent)} {percent:.1f}%

Speed: {speed/1024/1024:.2f} MB/s
ETA: {int(eta)}s
Elapsed: {int(elapsed)}s
"""

    try:
        await msg.edit(text)
    except:
        pass


@app.on_message(filters.command("start"))
async def start(_, m):

    if m.from_user.id not in ALLOWED_USERS:
        return

    sessions[m.from_user.id] = {
        "files": [],
        "format": None,
        "level": None,
        "name": None
    }

    await m.reply(
        "📦 Dynamic Archiver\n\nUpload files to archive.\nWhen finished send /done"
    )


@app.on_message(filters.document | filters.video | filters.audio)
async def collect(_, m):

    user = m.from_user.id

    if user not in sessions:
        return

    size = m.document.file_size if m.document else 0

    if size > 2000 * 1024 * 1024:
        await m.reply("❌ File too large (2GB limit).")
        return

    sessions[user]["files"].append(m)

    name = m.document.file_name if m.document else "file"

    await m.reply(f"📁 Queued: {name}")


@app.on_message(filters.command("done"))
async def choose_format(_, m):

    user = m.from_user.id

    if user not in sessions or not sessions[user]["files"]:
        await m.reply("No files uploaded.")
        return

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("ZIP", callback_data="fmt_zip"),
                InlineKeyboardButton("7Z", callback_data="fmt_7z")
            ]
        ]
    )

    await m.reply("Choose archive format:", reply_markup=kb)


@app.on_callback_query(filters.regex("fmt_"))
async def choose_level(_, q):

    user = q.from_user.id
    sessions[user]["format"] = q.data.split("_")[1]

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Low ⚡️", callback_data="lvl_low"),
                InlineKeyboardButton("Medium ⚖️", callback_data="lvl_med"),
                InlineKeyboardButton("High 🗜", callback_data="lvl_high")
            ]
        ]
    )

    await q.message.edit("Select compression level:", reply_markup=kb)


@app.on_callback_query(filters.regex("lvl_"))
async def ask_name(_, q):

    user = q.from_user.id
    sessions[user]["level"] = q.data.split("_")[1]

    await q.message.edit("Send archive name.")


@app.on_message(filters.text & ~filters.command(["start", "done", "cancel"]))
async def process_archive(_, m):

    user = m.from_user.id

    if user not in sessions:
        return

    if sessions[user]["name"] is None:

        sessions[user]["name"] = m.text

        status = await m.reply("Preparing download...")

        try:

            start = time.time()
            paths = []

            for file_msg in sessions[user]["files"]:

                file_name = file_msg.document.file_name.replace("/", "_")
                path = os.path.join(DOWNLOAD_DIR, file_name)

                await file_msg.download(
                    file_name=path,
                    progress=progress,
                    progress_args=(status, "Downloading", start)
                )

                paths.append(path)

            await status.edit("⚡️ Compressing...")
            await asyncio.sleep(1)

            fmt = sessions[user]["format"]
            archive_name = f"{sessions[user]['name']}.{fmt}"
            archive_path = os.path.join(DOWNLOAD_DIR, archive_name)

            if fmt == "zip":

                compression = {
                    "low": zipfile.ZIP_DEFLATED,
                    "med": zipfile.ZIP_BZIP2,
                    "high": zipfile.ZIP_LZMA
                }[sessions[user]["level"]]

                with zipfile.ZipFile(archive_path, "w", compression=compression) as z:
                    for p in paths:
                        z.write(p, os.path.basename(p))

            else:

                level_map = {
                    "low": "1",
                    "med": "5",
                    "high": "9"
                }

                level = level_map[sessions[user]["level"]]
                file_list = " ".join(paths)

                os.system(f'7z a -t7z -mx={level} "{archive_path}" {file_list}')

            await status.edit("📤 Uploading archive...")

            await m.reply_document(
                archive_path,
                progress=progress,
                progress_args=(status, "Uploading", start)
            )

            await status.edit("✅ Done!")

            for p in paths:
                try:
                    os.remove(p)
                except:
                    pass

            try:
                os.remove(archive_path)
            except:
                pass

            sessions.pop(user)

        except Exception as e:

            await status.edit(f"❌ Error:\n{e}")

            sessions.pop(user, None)


@app.on_message(filters.command("cancel"))
async def cancel(_, m):

    user = m.from_user.id

    if user in sessions:
        sessions.pop(user)

    await m.reply("❌ Task cancelled.")


print("Dynamic Archiver Running...")
app.run()
