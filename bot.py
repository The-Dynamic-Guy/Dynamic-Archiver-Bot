import os
import zipfile
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from concurrent.futures import ThreadPoolExecutor

API_ID = 30291360
API_HASH = "0f7c28c9e4c3ae162d8f23e020d613b5"
BOT_TOKEN = "8796804309:AAFvMeFWGApWusd47tLiYc1ytFEa6VIhm5cE"

OWNER_ID = 6050411363
ALLOWED_USERS = [6050411363]  # add your friend's ID here later

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

app = Client("dynamic_archiver", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_files = {}
executor = ThreadPoolExecutor(max_workers=4)


@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "📦 Dynamic Archiver Bot\n\n"
        "Send files to compress.\n"
        "When finished send /done"
    )


@app.on_message(filters.document | filters.video | filters.audio)
async def collect_files(client, message: Message):

    user_id = message.from_user.id

    if user_id not in ALLOWED_USERS:
        return

    if user_id not in user_files:
        user_files[user_id] = []

    msg = await message.reply("📥 Downloading file...")

    file_path = await message.download(file_name=DOWNLOAD_FOLDER)

    user_files[user_id].append(file_path)

    await msg.edit(f"✅ Added: {os.path.basename(file_path)}")


@app.on_message(filters.command("done"))
async def compress_files(client, message: Message):

    user_id = message.from_user.id

    if user_id not in user_files or not user_files[user_id]:
        await message.reply("No files to compress.")
        return

    files = user_files[user_id]

    status = await message.reply("⚡ Compressing files...")

    zip_name = f"{user_id}_archive.zip"
    zip_path = os.path.join(DOWNLOAD_FOLDER, zip_name)

    def zip_task():
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as z:
            for f in files:
                z.write(f, os.path.basename(f))

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, zip_task)

    await status.edit("📤 Uploading archive...")

    await client.send_document(
        message.chat.id,
        zip_path
    )

    await status.edit("✅ Archive sent!")

    for f in files:
        os.remove(f)

    os.remove(zip_path)

    user_files[user_id] = []


@app.on_message(filters.command("cancel"))
async def cancel(client, message):

    user_id = message.from_user.id

    if user_id in user_files:
        for f in user_files[user_id]:
            if os.path.exists(f):
                os.remove(f)

    user_files[user_id] = []

    await message.reply("❌ Task cancelled and files cleared.")


print("Dynamic Archiver Bot Running...")
app.run()
