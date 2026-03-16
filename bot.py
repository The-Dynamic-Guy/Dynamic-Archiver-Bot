import os
import time
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = 30291360
API_HASH = "0f7c28c9e4c3ae162d8f23e020d613b5
BOT_TOKEN = "8796804309:AAEuZ31sWkY8XMJF5ogORBDYC3fw5xK0nYE"

ALLOWED_USERS = [6050411363, 1723943834]

DOWNLOAD_DIR = "files"
MAX_SPLIT_SIZE = 1900 * 1024 * 1024

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Client(
    "dynamic_archiver",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

sessions = {}


def bar(p):
    f = int(p / 10)
    return "█" * f + "░" * (10 - f)


async def progress(current, total, msg, stage, start):

    percent = current * 100 / total
    elapsed = time.time() - start
    speed = current / elapsed if elapsed else 0
    eta = (total - current) / speed if speed else 0

    text = f"""
📦 Dynamic Archiver Elite

Stage: {stage}
Progress: {bar(percent)} {percent:.1f}%

Speed: {speed/1024/1024:.2f} MB/s
ETA: {int(eta)}s
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
        "name": None,
        "password": None
    }

    await m.reply(
        "📦 Dynamic Archiver Elite\n\nUpload files then send /done"
    )


@app.on_message(filters.document | filters.video | filters.audio)
async def collect(_, m):

    user = m.from_user.id

    if user not in sessions:
        return

    sessions[user]["files"].append(m)

    name = m.document.file_name if m.document else "file"

    await m.reply(f"📁 Added: {name}")


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

    await m.reply("Choose archive format", reply_markup=kb)


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
        "Send archive name.\n\nOptional password:\n\nexample:\narchive | mypass"
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

        try:

            start = time.time()
            paths = []

            for msg in sessions[user]["files"]:

                fname = msg.document.file_name.replace("/", "_")

                path = os.path.join(DOWNLOAD_DIR, fname)

                await msg.download(
                    file_name=path,
                    progress=progress,
                    progress_args=(status, "Downloading", start)
                )

                paths.append(path)

            await status.edit("⚡ Compressing...")

            fmt = sessions[user]["format"]
            level_map = {"low": "1", "med": "5", "high": "9"}

            level = level_map[sessions[user]["level"]]

            archive_name = sessions[user]["name"]

            archive_path = os.path.join(DOWNLOAD_DIR, archive_name)

            cmd = [
                "7z",
                "a",
                f"-mx={level}",
                f"-v{MAX_SPLIT_SIZE}"
            ]

            if password:
                cmd.append(f"-p{password}")

            if fmt == "zip":
                cmd.append("-tzip")
            else:
                cmd.append("-t7z")

            cmd.append(archive_path)
            cmd += paths

            subprocess.run(cmd)

            await status.edit("Uploading archive...")

            parts = [
                os.path.join(DOWNLOAD_DIR, f)
                for f in os.listdir(DOWNLOAD_DIR)
                if f.startswith(archive_name)
            ]

            for p in parts:

                await m.reply_document(
                    p,
                    progress=progress,
                    progress_args=(status, "Uploading", start)
                )

            await status.edit("✅ Archive complete!")

            for f in paths + parts:
                try:
                    os.remove(f)
                except:
                    pass

            sessions.pop(user)

        except Exception as e:

            await status.edit(f"❌ Error\n{e}")

            sessions.pop(user, None)


print("Dynamic Archiver Elite Running")
app.run()

            password = sessions[user]["password"]
