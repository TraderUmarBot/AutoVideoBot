import os
import requests
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip
import openai
import random

# ============================
# 🔑 ENV VARIABLES
# ============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")  # новый ключ
openai.api_key = OPENAI_API_KEY

# ============================
# 🔥 /start
# ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот, который создаёт тематическое видео 🎬.\n\n"
        "Отправь мне текст, и я предложу SEO и видео!"
    )

# ============================
# 🔥 SEO генерация
# ============================
def generate_seo(prompt, language="ru", style="clickbait"):
    system_prompt = (
        f"Ты создаешь SEO для YouTube видео на языке {language}. "
        "Нужны: Title, Теги, Описание. "
        "Title кликабельный (clickbait) или спокойный (calm)."
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Тема видео: {prompt}. Стиль: {style}"}
            ],
            timeout=15
        )
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Ошибка генерации SEO: {e}"

# ============================
# 🔥 TTS через OpenAI
# ============================
def generate_voice(text, voice="alloy"):
    try:
        response = openai.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text
        )
        with open("voice.mp3", "wb") as f:
            f.write(response)
        return "voice.mp3"
    except Exception as e:
        raise Exception(f"Ошибка генерации голоса: {e}")

# ============================
# 🔥 Поиск тематических видео через Pexels API
# ============================
def get_thematic_videos(query, num=3):
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page={num}"
    r = requests.get(url, headers=headers).json()
    videos = []
    for i, video in enumerate(r.get("videos", [])):
        video_url = video["video_files"][0]["link"]
        local_path = f"stock_{i}.mp4"
        video_data = requests.get(video_url).content
        with open(local_path, "wb") as f:
            f.write(video_data)
        videos.append(local_path)
    if not videos:
        # Если ничего не найдено, берём дефолтные видео
        default = [
            "https://sample-videos.com/video123/mp4/720/big_buck_bunny_720p_1mb.mp4"
        ]
        for i, url in enumerate(default):
            data = requests.get(url).content
            path = f"stock_default_{i}.mp4"
            with open(path, "wb") as f:
                f.write(data)
            videos.append(path)
    return videos

# ============================
# 🔥 Создание видео с озвучкой
# ============================
def generate_video(stock_files, audio_path, vertical=True):
    clips = []
    width, height = (1080, 1920) if vertical else (1280, 720)
    for file in stock_files:
        clip = VideoFileClip(file).resize(newsize=(width, height)).subclip(0, 10)
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

    keyboard = [
        [
            InlineKeyboardButton("Русский 🇷🇺", callback_data="lang|ru"),
            InlineKeyboardButton("Английский 🇬🇧", callback_data="lang|en"),
        ]
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
            [
                InlineKeyboardButton("Вертикальное 🎥", callback_data="format|vertical"),
                InlineKeyboardButton("Горизонтальное 📺", callback_data="format|horizontal"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите формат видео:", reply_markup=reply_markup)

    elif data.startswith("format"):
        orientation = data.split("|")[1]
        vertical = orientation == "vertical"
        lang = context.user_data.get("language", "ru")
        text = context.user_data.get("text", "")

        # 1️⃣ SEO
        await query.edit_message_text("Генерируем SEO…")
        seo_text = generate_seo(text, language=lang)
        await query.message.reply_text(f"SEO создано:\n{seo_text}")

        # 2️⃣ Тематические видео
        await query.message.reply_text("Ищем тематические видео…")
        stock_files = get_thematic_videos(query=text, num=3)

        # 3️⃣ Озвучка
        await query.message.reply_text("Создаём озвучку…")
        voice = generate_voice(text)

        # 4️⃣ Видео
        await query.message.reply_text("Собираем финальное видео…")
        video = generate_video(stock_files, voice, vertical=vertical)

        # 5️⃣ Готово!
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
