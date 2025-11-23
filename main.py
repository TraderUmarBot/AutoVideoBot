import os
import requests
import threading
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

# ============================
# 🔥 /start
# ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бесплатный бот для создания видео 🎬.\n\n"
        "Отправь тему видео, и выбери язык, формат и длительность!"
    )

# ============================
# 🔥 SEO генерация (бесплатно)
# ============================
def generate_seo(prompt, language="ru"):
    title = f"Видео о {prompt}"
    description = f"Узнайте всё о {prompt}! Интересные факты и видео."
    tags = f"{prompt}, видео, интересное, факты"
    return f"**Title:** {title}\n**Описание:** {description}\n**Теги:** {tags}"

# ============================
# 🔥 Озвучка через gTTS (бесплатно)
# ============================
def generate_voice(text, lang="ru"):
    tts = gTTS(text, lang=lang)
    tts.save("voice.mp3")
    return "voice.mp3"

# ============================
# 🔥 Параллельная загрузка видео
# ============================
def download_video(url, path):
    try:
        r = requests.get(url)
        with open(path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"Ошибка скачивания {url}: {e}")

def get_thematic_videos(query, num=3):
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page={num}"
    r = requests.get(url, headers=headers).json()

    videos = []
    threads = []

    for i, video in enumerate(r.get("videos", [])):
        video_url = video["video_files"][0]["link"]
        local_path = f"stock_{i}.mp4"
        videos.append(local_path)
        t = threading.Thread(target=download_video, args=(video_url, local_path))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    if not videos:
        default = ["https://sample-videos.com/video123/mp4/720/big_buck_bunny_720p_1mb.mp4"]
        videos = []
        threads = []
        for i, url in enumerate(default):
            path = f"stock_default_{i}.mp4"
            t = threading.Thread(target=download_video, args=(url, path))
            t.start()
            threads.append(t)
            videos.append(path)
        for t in threads:
            t.join()

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
    final_clip.write_videofile("result.mp4", fps=24)
    return "result.mp4"

# ============================
# 🔥 Обработка текста
# ============================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    context.user_data["text"] = user_text

    # Выбор языка
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

        # Выбор формата видео
        keyboard = [
            [InlineKeyboardButton("Вертикальное 🎥", callback_data="format|vertical"),
             InlineKeyboardButton("Горизонтальное 📺", callback_data="format|horizontal")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите формат видео:", reply_markup=reply_markup)

    elif data.startswith("format"):
        orientation = data.split("|")[1]
        vertical = orientation == "vertical"
        context.user_data["vertical"] = vertical

        # Выбор длительности видео
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

        # Количество клипов = длительность / 10 сек на клип
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
        video = generate_video(stock_files, voice, vertical=vertical, clip_length=clip_length)

        await query.message.reply_video(video=InputFile("result.mp4"))
        await query.message.reply_text("✅ Видео готово!")

# ============================
# 🔥 MAIN
# ============================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(CallbackQueryHandler(handle_button))

    print("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
