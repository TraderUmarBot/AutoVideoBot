#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoVideoBot - Telegram bot for automatic YouTube video generation.
Features:
- Accepts user prompt + optional duration
- Generates script (OpenAI or local fallback)
- Generates images (Replicate/Stability if configured, otherwise PIL placeholders)
- Generates TTS audio (gTTS by default; ElevenLabs optional)
- Assembles mp4 via moviepy (requires ffmpeg)
- Asynchronous background job queue (SQLite) to avoid blocking updates
- Basic free-credits tracking per-user (3 free jobs)
- Ready to run in Docker (see Dockerfile)
"""

import os
import logging
import uuid
import tempfile
import asyncio
import math
import time
import sqlite3
from typing import List, Optional
from io import BytesIO

# Старое
# from telegram import Update, ChatAction, InputFile

# Новое
from telegram import Update, InputFile
from telegram.constants import ChatAction
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

import requests
from telegram import Update, ChatAction, InputFile
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

# Optional libs; if not installed your environment should still work with fallbacks
try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# -------- CONFIG / ENV --------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # required
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # optional
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")  # optional
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")  # optional
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")  # optional
FREE_JOBS_PER_USER = int(os.getenv("FREE_JOBS_PER_USER", "3"))

# video settings
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1280"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "720"))
DEFAULT_BG_COLOR = (18, 18, 18)
FPS = int(os.getenv("FPS", "24"))

# database path
DB_PATH = os.getenv("DB_PATH", "jobs.db")

if OPENAI_API_KEY and OPENAI_AVAILABLE:
    openai.api_key = OPENAI_API_KEY

# -------- logging --------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("autovideobot")

# -------- conversation states --------
PROMPT = 0

# -------- minimal SQLite wrapper --------
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            chat_id INTEGER,
            prompt TEXT,
            duration INTEGER,
            status TEXT,
            result_path TEXT,
            created_at REAL,
            updated_at REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            free_used INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn

DB = init_db()

# -------- helpers: DB operations --------
def create_job(user_id: int, chat_id: int, prompt: str, duration: int) -> str:
    job_id = uuid.uuid4().hex
    ts = time.time()
    cur = DB.cursor()
    cur.execute(
        "INSERT INTO jobs (id, user_id, chat_id, prompt, duration, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (job_id, user_id, chat_id, prompt, duration, "queued", ts, ts),
    )
    DB.commit()
    return job_id

def update_job_status(job_id: str, status: str, result_path: Optional[str] = None):
    ts = time.time()
    cur = DB.cursor()
    if result_path:
        cur.execute("UPDATE jobs SET status=?, result_path=?, updated_at=? WHERE id=?", (status, result_path, ts, job_id))
    else:
        cur.execute("UPDATE jobs SET status=?, updated_at=? WHERE id=?", (status, ts, job_id))
    DB.commit()

def get_job(job_id: str):
    cur = DB.cursor()
    cur.execute("SELECT id,user_id,chat_id,prompt,duration,status,result_path,created_at,updated_at FROM jobs WHERE id=?", (job_id,))
    return cur.fetchone()

def inc_user_free(user_id: int) -> int:
    cur = DB.cursor()
    cur.execute("SELECT free_used FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users (user_id, free_used) VALUES (?,?)", (user_id, 1))
        DB.commit()
        return 1
    else:
        used = row[0] + 1
        cur.execute("UPDATE users SET free_used=? WHERE user_id=?", (used, user_id))
        DB.commit()
        return used

def get_user_free_used(user_id: int) -> int:
    cur = DB.cursor()
    cur.execute("SELECT free_used FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 0

# -------- script generation --------
def generate_script(prompt: str, duration: int = 60) -> str:
    """
    Use OpenAI if available, otherwise use local fallback.
    """
    if OPENAI_API_KEY and OPENAI_AVAILABLE:
        try:
            logger.info("Generating script via OpenAI")
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role":"system","content":"Ты помогаешь написать сценарии для YouTube-видео, разбивая на сцены с указанием длительности каждой."},
                    {"role":"user","content":f"Сделай подробный сценарий для видео на {duration} секунд по теме: {prompt}. Разбей на сцены с примерной длительностью."}
                ],
                temperature=0.7,
                max_tokens=700
            )
            text = resp["choices"][0]["message"]["content"].strip()
            return text
        except Exception as e:
            logger.exception("OpenAI script generation failed: %s", e)
    # fallback
    logger.info("Using local fallback script generator")
    base = prompt.strip().rstrip(".!?")
    bullets = [
        f"Вступление — кратко о теме: «{base}».",
        "Ключевая идея / демонстрация примера.",
        "3 практических шага или совета.",
        "Дополнительные лайфхаки и предупреждения.",
        "Заключение и призыв к действию (подписка, лайк, комментарий)."
    ]
    total = duration
    portions = [0.08, 0.25, 0.45, 0.12, 0.10]
    seconds = [max(2, int(total * p)) for p in portions]
    diff = total - sum(seconds)
    seconds[2] += diff
    lines = []
    for i, b in enumerate(bullets):
        lines.append(f"Сцена {i+1} ({seconds[i]}s): {b}")
    return "\n\n".join(lines)

# -------- image generation (external placeholders) --------
def generate_images_external(prompt: str, count: int = 6) -> List[str]:
    """
    Tries to call Replicate/Stability (placeholder). If not available or fails, returns [].
    For production, implement proper API calls + polling for chosen model.
    """
    out = []
    # NOTE: this is intentionally generic placeholder — real API integration needs model/version details
    if REPLICATE_API_TOKEN:
        logger.info("Replicate token present, but external integration not implemented in this template.")
    if STABILITY_API_KEY:
        logger.info("Stability key present, but external integration not implemented in this template.")
    return out

def make_placeholder_images(script_text: str, count: int = 6) -> List[str]:
    """
    Create simple PNG frames with chunks of script text.
    """
    tmp = []
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
    except Exception:
        font = ImageFont.load_default()

    lines = [line.strip() for line in script_text.splitlines() if line.strip()]
    if not lines:
        lines = [script_text]
    # produce up to count frames by chunking
    combined = " ".join(lines)
    chunk_len = max(80, len(combined) // count)
    chunks = [combined[i:i+chunk_len] for i in range(0, len(combined), chunk_len)]
    chunks = chunks[:count] if len(chunks) >= count else chunks + [""]*(count - len(chunks))

    for idx, chunk in enumerate(chunks):
        im = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), color=DEFAULT_BG_COLOR)
        draw = ImageDraw.Draw(im)
        margin = 60
        y = 80
        # naive wrap
        words = chunk.split(" ")
        line = ""
        maxw = VIDEO_WIDTH - margin*2
        for w in words:
            test = (line + " " + w).strip()
            w_w, h = draw.textsize(test, font=font)
            if w_w > maxw and line:
                draw.text((margin, y), line, font=font, fill=(240,240,240))
                y += h + 8
                line = w
            else:
                line = test
        if line:
            draw.text((margin, y), line, font=font, fill=(240,240,240))
        # footer
        draw.text((margin, VIDEO_HEIGHT-70), f"AutoVideoBot • {idx+1}/{len(chunks)}", font=font, fill=(160,160,160))
        path = os.path.join(tempfile.gettempdir(), f"frame_{uuid.uuid4().hex}.png")
        im.save(path, "PNG")
        tmp.append(path)
    return tmp

# -------- TTS (gTTS by default; ElevenLabs optional) --------
def generate_tts_gtts(text: str, lang: str = "ru") -> str:
    path = os.path.join(tempfile.gettempdir(), f"audio_{uuid.uuid4().hex}.mp3")
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(path)
    return path

def generate_tts_elevenlabs(text: str, voice: str = "alloy", output_path: Optional[str] = None) -> Optional[str]:
    """
    Optional ElevenLabs TTS (requires ELEVENLABS_API_KEY). Simple blocking implementation.
    """
    if not ELEVENLABS_API_KEY:
        return None
    # This is a basic example; consult ElevenLabs docs for up-to-date API usage.
    url = "https://api.elevenlabs.io/v1/text-to-speech/" + voice
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"text": text, "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    out = output_path or os.path.join(tempfile.gettempdir(), f"audio_{uuid.uuid4().hex}.mp3")
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60)
        if r.ok:
            with open(out, "wb") as f:
                f.write(r.content)
            return out
        else:
            logger.warning("ElevenLabs TTS failed: %s %s", r.status_code, r.text)
    except Exception as e:
        logger.exception("ElevenLabs request failed: %s", e)
    return None

# -------- video assembly --------
def assemble_video(image_paths: List[str], audio_path: str, output_path: str):
    """
    Create mp4 by assigning equal durations for each image to match audio length.
    """
    audio = AudioFileClip(audio_path)
    total = audio.duration
    n = max(1, len(image_paths))
    per = total / n
    clips = []
    for p in image_paths:
        clip = ImageClip(p).set_duration(per).resize((VIDEO_WIDTH, VIDEO_HEIGHT))
        clips.append(clip)
    video = concatenate_videoclips(clips, method="compose")
    video = video.set_audio(audio)
    # writing video (might take time)
    video.write_videofile(output_path, fps=FPS, audio_codec="aac", verbose=False, logger=None)
    video.close()
    audio.close()
    for c in clips:
        c.close()

# -------- background worker --------
async def process_job(application, job_id: str):
    """
    Background job runner: updates DB and writes messages to user when done.
    """
    job = get_job(job_id)
    if not job:
        logger.error("Job not found: %s", job_id)
        return
    _, user_id, chat_id, prompt, duration, status, result_path, *_ = job
    try:
        update_job_status(job_id, "processing")
        # 1. script
        application.bot.send_message(chat_id=chat_id, text=f"🔧 Обрабатываю: {prompt}\nГенерирую сценарий...")
        script = generate_script(prompt, duration)
        application.bot.send_message(chat_id=chat_id, text="🖼️ Генерирую кадры (может занять время)...")
        # 2. images
        images = generate_images_external(prompt, count=max(3, min(10, math.ceil(duration/6))))
        if not images:
            images = make_placeholder_images(script, count=max(3, min(10, math.ceil(duration/6))))
        application.bot.send_message(chat_id=chat_id, text="🔊 Генерирую голос...")
        # 3. audio (prefer ElevenLabs if key provided)
        audio = None
        if ELEVENLABS_API_KEY:
            audio = generate_tts_elevenlabs(script)
        if not audio:
            audio = generate_tts_gtts(script, lang="ru")
        application.bot.send_message(chat_id=chat_id, text="🎬 Склеиваю видео...")
        # 4. assemble
        out_path = os.path.join(tempfile.gettempdir(), f"video_{uuid.uuid4().hex}.mp4")
        assemble_video(images, audio, out_path)
        update_job_status(job_id, "done", result_path=out_path)
        # send video
        application.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)
        with open(out_path, "rb") as f:
            application.bot.send_video(chat_id=chat_id, video=InputFile(f, filename="auto_video.mp4"))
        application.bot.send_message(chat_id=chat_id, text="✅ Готово! Вот твоё видео.")
    except Exception as e:
        logger.exception("Job processing failed: %s", e)
        update_job_status(job_id, "failed")
        try:
            application.bot.send_message(chat_id=chat_id, text="❌ Произошла ошибка при создании видео. Попробуйте позже.")
        except Exception:
            pass
    finally:
        # cleanup temp images/audio/result if stored in temp dir
        try:
            job = get_job(job_id)
            if job and job[6]:
                # result_path is stored in DB; we keep it for now (could implement storage)
                pass
        except Exception:
            pass

# -------- telegram handlers --------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я AutoVideoBot — создаю видео по описанию.\n\n"
        "Команды:\n"
        "/newvideo - создать видео\n"
        "/status <job_id> - статус задачи\n"
        "/credits - узнать сколько бесплатных использовано\n"
        "/help - помощь"
    )

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Как создать видео:\n"
        "1) Нажми /newvideo\n"
        "2) Введи тему и опционально длительность через запятую (в секундах), например:\n"
        "   Как сделать турбо-омлет, 45\n\n"
        f"У каждого пользователя {FREE_JOBS_PER_USER} бесплатных запросов. Для платного доступа интеграция оплат доступна отдельно."
    )

async def newvideo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Введи тему/идею для видео. Можно указать длительность через запятую (секунды).\n"
        "Пример: Три лайфхака по экономии, 60"
    )
    return PROMPT

async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    duration = 60
    if "," in text:
        parts = text.rsplit(",", 1)
        if parts[1].strip().isdigit():
            duration = max(10, min(8*60, int(parts[1].strip())))
            prompt = parts[0].strip()
        else:
            prompt = text
    else:
        prompt = text

    user_id = update.effective_user.id
    used = get_user_free_used(user_id)
    if used >= FREE_JOBS_PER_USER:
        await update.message.reply_text(
            f"У тебя уже {used} бесплатных запросов (лимит {FREE_JOBS_PER_USER}).\n"
            "Чтобы продолжить, подключи подписку (не реализована автоматически) или снизь частоту.\n"
            "В демонстрационной версии у нас нет платёжного шлюза — можно выжать бесплатные тесты."
        )
        # For demo we still allow job; comment next line to block
        # return ConversationHandler.END

    # create job
    job_id = create_job(user_id, update.effective_chat.id, prompt, duration)
    await update.message.reply_text(f"Задача принята в очередь. ID: {job_id}\nЯ начну обработку и пришлю результат сюда.")
    inc_user_free(user_id)
    # run background processing
    asyncio.create_task(process_job(context.application, job_id))
    return ConversationHandler.END

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /status <job_id>")
        return
    job_id = args[0]
    job = get_job(job_id)
    if not job:
        await update.message.reply_text("Задача не найдена.")
        return
    _, user_id, chat_id, prompt, duration, status, result_path, created_at, updated_at = job
    msg = f"ID: {job_id}\nСтатус: {status}\nТема: {prompt}\nДлительность: {duration}s\nСоздана: {time.ctime(created_at)}"
    await update.message.reply_text(msg)

async def credits_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    used = get_user_free_used(user_id)
    await update.message.reply_text(f"Использовано бесплатных запросов: {used}/{FREE_JOBS_PER_USER}")

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отмена.")
    return ConversationHandler.END

# -------- main --------
def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not set, exiting.")
        raise SystemExit("Please set TELEGRAM_TOKEN env var.")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("newvideo", newvideo_start)],
        states={PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt)]},
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        conversation_timeout=300,
    )

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("credits", credits_handler))
    app.add_handler(conv)

    logger.info("Starting bot (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
