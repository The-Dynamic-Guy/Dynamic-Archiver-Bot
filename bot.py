import os
import time
import shutil
import asyncio
import subprocess
import psutil

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

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


def progress_bar(percent: float) -> str:
    filled = int(percent / 10)
    return "█" * filled + "░" * (10 - filled)


def disk_status() -> float:
    return psutil.disk_usage("/").percent


def ram_status() -> float:
    return psutil.virtual_memory().percent


def cleanup_all() -> None:
    if not os.path.exists(DOWNLOAD_DIR):
        return
    for name in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, name)
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass


def cleanup_user_files(paths: list[str], archive_prefix: str) -> None:
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    for name in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, name)
        try:
            if name.startswith(archive_prefix) and os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass


async def render_progress(
    msg,
    stage: str,
    percent: float,
    speed_mb: float = 0.0,
    eta_sec: int = 0,
    file_count: int = 0
) -> None:
    text = (
        "╭━━━ Dynamic Archiver ━━━╮\n\n"
        f"⚡ Stage : {stage}\n\n"
        f"{progress_bar(percent)} {percent:.1f}%\n\n"
        f"🚀 Speed : {speed_mb:.2f} MB/s\n"
        f"⏳ ETA   : {eta_sec}s\n"
        f"📦 Files : {file_count}\n"
        f"💾 Disk  : {disk_status()}%\n"
        f"🧠 RAM   : {ram_status()}%\n\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━╯"
    )
    try:
        await msg.edit(text)
    except Exception:
        pass


async def upload_with_retry(message, file_path: str, status_msg, start_time: float) -> bool:
    for _ in range(3):
        try:
            await message.reply_document(
                file_path,
                progress=telegram_progress,
                progress_args=(status_msg, "Uploading", start_time, 1)
            )
            return True
        except Exception:
            await asyncio.sleep(3)
    return False


async def telegram_progress(current, total, msg, stage, start, file_count=1):
    percent = (current / total * 100) if total else 0
    elapsed = max(time.time() - start, 0.001)
    speed_mb = (current / elapsed) / 1024 / 1024
    remaining = max(total - current, 0)
    eta_sec = int(remaining / (current / elapsed)) if current > 0 else 0
    await render_progress(msg, stage, percent, speed_mb, eta_sec, file_count)


cleanup_all()


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
        "📦 Dynamic Archiver\n\n"
        "Upload files to archive.\n"
        "When finished send /done"
    )


@app.on_message(filters.document | filters.video | filters.audio)
async def collect(_, m):
    user = m.from_user.id

    if user not in sessions:
        return

    file_name = getattr(m.document, "file_name", None) or "file"
    sessions[user]["files"].append(m)

    await m.reply(f"📁 Added: {file_name}")


@app.on_message(filters.command("done"))
async def choose_format(_, m):
    user = m.from_user.id

    if user not in sessions or not sessions[user]["files"]:
        await m.reply("Upload files first.")
        return

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ZIP", callback_data="fmt_zip"),
            InlineKeyboardButton("7Z", callback_data="fmt_7z")
        ]
    ])

    await m.reply("Choose archive format:", reply_markup=kb)


@app.on_callback_query(filters.regex(r"^fmt_"))
async def choose_level(_, q):
    user = q.from_user.id

    if user not in sessions:
        await q.answer("Start again with /start", show_alert=True)
        return

    sessions[user]["format"] = q.data.split("_", 1)[1]

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Low", callback_data="lvl_low"),
            InlineKeyboardButton("Medium", callback_data="lvl_med"),
            InlineKeyboardButton("High", callback_data="lvl_high")
        ]
    ])

    await q.message.edit("Compression level:", reply_markup=kb)
    await q.answer()


@app.on_callback_query(filters.regex(r"^lvl_"))
async def ask_name(_, q):
    user = q.from_user.id

    if user not in sessions:
        await q.answer("Start again with /start", show_alert=True)
        return

    sessions[user]["level"] = q.data.split("_", 1)[1]

    await q.message.edit(
        "Send archive name.\n\n"
        "Optional password format:\n"
        "archive_name | password123"
    )
    await q.answer()


@app.on_message(filters.text & ~filters.command(["start", "done", "cancel"]))
async def process_text(_, m):
    user = m.from_user.id

    if user not in sessions:
        return

    if sessions[user]["name"] is not None:
        return

    text_value = m.text.strip()
    if not text_value:
        return

    parts = text_value.split("|", 1)
    archive_name = parts[0].strip().replace("/", "_")
    password = parts[1].strip() if len(parts) > 1 else None

    if not archive_name:
        await m.reply("Please send a valid archive name.")
        return

    sessions[user]["name"] = archive_name
    sessions[user]["password"] = password

    status = await m.reply("Preparing download...")

    downloaded_paths = []
    start_time = time.time()

    try:
        total_files = len(sessions[user]["files"])

        for index, msg_obj in enumerate(sessions[user]["files"], start=1):
            file_name = getattr(msg_obj.document, "file_name", None) or f"file_{index}"
            file_name = file_name.replace("/", "_")
            file_path = os.path.join(DOWNLOAD_DIR, file_name)

            await msg_obj.download(
                file_name=file_path,
                progress=telegram_progress,
                progress_args=(status, f"Downloading ({index}/{total_files})", start_time, total_files)
            )

            downloaded_paths.append(file_path)

        await render_progress(status, "Compressing", 0, 0.0, 0, total_files)

        level_map = {"low": "1", "med": "5", "high": "9"}
        level = level_map[sessions[user]["level"]]

        fmt = sessions[user]["format"]
        archive_base = os.path.join(DOWNLOAD_DIR, archive_name)

        cmd = [
            "7z",
            "a",
            "-bsp1",
            "-bso1",
            "-mmt=on",
            "-m0=lzma2",
            f"-mx={level}",
            f"-v{MAX_SPLIT_SIZE}"
        ]

        if password:
            cmd.append(f"-p{password}")

        if fmt == "zip":
            cmd.append("-tzip")
            archive_target = archive_base + ".zip"
        else:
            cmd.append("-t7z")
            archive_target = archive_base + ".7z"

        cmd.append(archive_target)
        cmd.extend(downloaded_paths)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        compress_percent = 0
        last_update = time.time()

        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line and proc.poll() is not None:
                break

            line = line.strip()

            # 7z often emits percentage lines like " 23%"
            if "%" in line:
                for token in line.split():
                    if token.endswith("%"):
                        raw = token[:-1]
                        if raw.isdigit():
                            compress_percent = max(0, min(100, int(raw)))
                            break

            # fallback slow animation if parser gets nothing
            if time.time() - last_update >= 1:
                if compress_percent == 0:
                    compress_percent = min(compress_percent + 2, 95)
                await render_progress(status, "Compressing", compress_percent, 0.0, 0, total_files)
                last_update = time.time()

        return_code = proc.wait()
        if return_code != 0:
            raise RuntimeError("Compression failed. 7z returned an error.")

        await render_progress(status, "Compressing", 100, 0.0, 0, total_files)

        archive_parts = sorted(
            os.path.join(DOWNLOAD_DIR, f)
            for f in os.listdir(DOWNLOAD_DIR)
            if f.startswith(archive_name)
        )

        if not archive_parts:
            raise RuntimeError("No archive was created.")

        for idx, part in enumerate(archive_parts, start=1):
            await status.edit(f"Uploading archive part {idx}/{len(archive_parts)}...")
            ok = await upload_with_retry(m, part, status, start_time)
            if not ok:
                raise RuntimeError(f"Failed to upload: {os.path.basename(part)}")

        await status.edit("✅ Archive complete!")

    except Exception as e:
        await status.edit(f"❌ Error:\n{e}")

    finally:
        cleanup_user_files(downloaded_paths, archive_name)
        sessions.pop(user, None)


@app.on_message(filters.command("cancel"))
async def cancel(_, m):
    user = m.from_user.id

    if user in sessions:
        sessions.pop(user, None)

    await m.reply("❌ Task cancelled.")


if not API_ID or not API_HASH or not BOT_TOKEN:
    raise ValueError("Missing API_ID, API_HASH, or BOT_TOKEN in Railway Variables.")

print("Dynamic Archiver Titan Running")
app.run()
