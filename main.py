import os
import requests
import threading
import tempfile
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip
from gtts import gTTS

# ============================
# 🔑 ENV VARIABLES
# ============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")  # бесплатный ключ

TMP_DIR = tempfile.gettempdir()  # временная папка для скачанных видео

# ============================
# 🔥 /start
# ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бесплатный бот для создания видео 🎬.\n"
        "Отправь тему видео и выбери язык, формат и длительность!"
    )

# ============================
# 🔥 SEO генерация
# ============================
def generate_seo(prompt, language="ru"):
    title = f"Видео о {prompt}"
    description = f"Узнайте всё о {prompt}! Интересные факты и видео."
    tags = f"{prompt}, видео, интересное, факты"
    return f"**Title:** {title}\n**Описание:** {description}\n**Теги:** {tags}"

# ============================
# 🔥 Озвучка через gTTS
# ============================
def generate_voice(text, lang="ru"):
    voice_path = os.path.join(TMP_DIR, "voice.mp3")
    tts = gTTS(text, lang=lang)
    tts.save(voice_path)
    return voice_path

# ============================
# 🔥 Скачивание видео
# ============================
def download_video(url, path):
    try:
        r = requests.get(url, timeout=20)
        with open(path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"Ошибка скачивания {url}: {e}")

def get_thematic_videos(query, num=3):
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page={num}"
    videos = []

    try:
        r = requests.get(url, headers=headers, timeout=20).json()
        vids = r.get("videos", [])
    except Exception as e:
        print(f"Ошибка Pexels API: {e}")
        vids = []

    threads = []

    if vids:
        for i, video in enumerate(vids):
            video_url = video["video_files"][0]["link"]
            local_path = os.path.join(TMP_DIR, f"stock_{i}.mp4")
            videos.append(local_path)
            t = threading.Thread(target=download_video, args=(video_url, local_path))
            t.start()
            threads.append(t)
    else:
        # Дефолтное видео, если Pexels не сработал
        default_url = "https://sample-videos.com/video123/mp4/720/big_buck_bunny_720p_1mb.mp4"
        local_path = os.path.join(TMP_DIR, "stock_default_0.mp4")
        videos.append(local_path)
        t = threading.Thread(target=download_video, args=(default_url, local_path))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    # Проверка
    for v in videos:
        if not os.path.exists(v):
            raise Exception(f"Файл {v} не найден!")

    return videos

# ============================
# 🔥 Создание видео
# ============================
def generate_video(stock_files, audio_path, vertical=True, clip_length=10):
    clips = []
    width, height = (1080, 1920) if vertical else (1280, 720)
    for file in stock_files:
        clip = VideoFileClip(file).resize(newsize=(width, height)).subclip(0, clip_length)
        clips.append(clip)
    final_clip = concatenate_videoclips(clips)
    audio = AudioFileClip(audio_path)
    final_clip = final_clip.set_audio(audio)
    out_path = os.path.join(TMP_DIR, "result.mp4")
    final_clip.write_videofile(out_path, fps=24)
    return out_path

# ============================
# 🔥 Обработка текста
# ============================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    context.user_data["text"] = user_text

    keyboard = [
        [InlineKeyboardButton("Русский 🇷🇺", callback_data="lang|ru"),
         InlineKeyboardButton("Английский 🇬🇧", callback_data="lang|en")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите язык видео:", reply_markup=reply_markup)

# ============================
# 🔥 Обработка кнопок
# ============================
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("lang"):
        lang = data.split("|")[1]
        context.user_data["language"] = lang

        keyboard = [
            [InlineKeyboardButton("Вертикальное 🎥", callback_data="format|vertical"),
             InlineKeyboardButton("Горизонтальное 📺", callback_data="format|horizontal")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите формат видео:", reply_markup=reply_markup)

    elif data.startswith("format"):
        orientation = data.split("|")[1]
        context.user_data["vertical"] = orientation == "vertical"

        keyboard = [
            [InlineKeyboardButton("30 сек ⏱", callback_data="duration|30"),
             InlineKeyboardButton("1 мин 🕐", callback_data="duration|60")],
            [InlineKeyboardButton("5 мин ⏳", callback_data="duration|300"),
             InlineKeyboardButton("10 мин ⏳", callback_data="duration|600"),
             InlineKeyboardButton("15 мин ⏳", callback_data="duration|900")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите длительность видео:", reply_markup=reply_markup)

    elif data.startswith("duration"):
        duration_sec = int(data.split("|")[1])
        vertical = context.user_data.get("vertical", True)
        lang = context.user_data.get("language", "ru")
        text = context.user_data.get("text", "")

        clip_length = 10
        num_clips = max(1, duration_sec // clip_length)

        await query.edit_message_text("Генерируем SEO…")
        seo_text = generate_seo(text, language=lang)
        await query.message.reply_text(f"SEO создано:\n{seo_text}")

        await query.message.reply_text("Ищем тематические видео…")
        stock_files = get_thematic_videos(query=text, num=num_clips)

        await query.message.reply_text("Создаём озвучку…")
        voice = generate_voice(text, lang=lang)

        await query.message.reply_text("Собираем финальное видео…")
        video_path = generate_video(stock_files, voice, vertical=vertical, clip_length=clip_length)

        await query.message.reply_video(video=InputFile(video_path))
        await query.message.reply_text("✅ Видео готово!")

# ============================
# 🔥 MAIN
# ============================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(CallbackQueryHandler(handle_button))

    print("Bot started! (background worker)")
    app.run_polling()

if __name__ == "__main__":
    main()
