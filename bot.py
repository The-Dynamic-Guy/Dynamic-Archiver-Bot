with zipfile.ZipFile(archive_path, "w", compression=compression) as zf:
        for idx, p in enumerate(paths, start=1):
            zf.write(p, os.path.basename(p))
            percent = idx * 100 / total_files if total_files else 100
            await render_progress(status_msg, "Compressing", percent, 0.0, 0, total_files)
            await asyncio.sleep(0)


async def create_7z_archive(paths: list[str], archive_path: str, level: str, password: str | None, status_msg, total_files: int):
    filters_map = {
        "low": [{"id": py7zr.FILTER_COPY}],
        "med": [{"id": py7zr.FILTER_LZMA2, "preset": 5}],
        "high": [{"id": py7zr.FILTER_LZMA2, "preset": 9}]
    }
    archive_kwargs = {
        "mode": "w",
        "filters": filters_map[level]
    }
    if password:
        archive_kwargs["password"] = password

    with py7zr.SevenZipFile(archive_path, **archive_kwargs) as zf:
        for idx, p in enumerate(paths, start=1):
            zf.write(p, arcname=os.path.basename(p))
            percent = idx * 100 / total_files if total_files else 100
            await render_progress(status_msg, "Compressing", percent, 0.0, 0, total_files)
            await asyncio.sleep(0)


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

    fmt = sessions[user]["format"]
    if fmt == "7z":
        prompt = (
            "Send archive name.\n\n"
            "Optional password format:\n"
            "archive_name | password123"
        )
    else:
        prompt = "Send archive name."

    await q.message.edit(prompt)
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

    fmt = sessions[user]["format"]
    
    if fmt == "7z":
        parts = text_value.split("|", 1)
        archive_name = parts[0].strip().replace("/", "_")
        password = parts[1].strip() if len(parts) > 1 else None
    else:
        archive_name = text_value.replace("/", "_")
        password = None

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

        level = sessions[user]["level"]

        if fmt == "zip":
            archive_path = os.path.join(DOWNLOAD_DIR, archive_name + ".zip")
            await create_zip_archive(downloaded_paths, archive_path, level, status, total_files)
        else:
            archive_path = os.path.join(DOWNLOAD_DIR, archive_name + ".7z")
            await create_7z_archive(downloaded_paths, archive_path, level, password, status, total_files)

        archive_parts = split_file_if_needed(archive_path)
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
