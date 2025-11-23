import os
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
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from PIL import Image
import requests
import openai

# ============================
# 🔑 ENV VARIABLES
# ============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

# ============================
# 🔥 /start
# ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот, который создаёт видео по твоему сценарию 🎬.\n\n"
        "Отправь мне текст, и я предложу SEO и видео!"
    )

# ============================
# 🔥 SEO генерация
# ============================
def generate_seo(prompt, language="ru", style="clickbait"):
    system_prompt = (
        f"Ты создаешь SEO для YouTube видео на языке {language}. "
        "Нужны: Title, Теги, Описание. "
        "Title кликабельный (clickbait) или документальный (calm)."
    )
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Тема видео: {prompt}. Стиль: {style}"}
        ],
    )
    return response["choices"][0]["message"]["content"]

# ============================
# 🔥 AI картинка
# ============================
def generate_image(prompt, size="1024x1024"):
    url = "https://api.openai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {"prompt": prompt, "size": size}

    response = requests.post(url, headers=headers, json=payload).json()
    image_url = response["data"][0]["url"]

    img = Image.open(requests.get(image_url, stream=True).raw)
    img.save("frame.png")
    return "frame.png"

# ============================
# 🔥 Реалистичный TTS через OpenAI
# ============================
def generate_voice(text, voice="alloy"):
    response = openai.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=text
    )
    with open("voice.mp3", "wb") as f:
        f.write(response)
    return "voice.mp3"

# ============================
# 🔥 Создание многосценочного видео
# ============================
def generate_video(images, audio_path, vertical=True):
    clips = []
    width, height = (1080, 1920) if vertical else (1280, 720)
    for img_path in images:
        clip = ImageClip(img_path).set_duration(7).resize(newsize=(width, height))
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
    # Выбор языка
    keyboard = [
        [
            InlineKeyboardButton("Русский 🇷🇺", callback_data=f"lang|ru|{user_text}"),
            InlineKeyboardButton("Английский 🇬🇧", callback_data=f"lang|en|{user_text}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите язык видео:", reply_markup=reply_markup)

# ============================
# 🔥 Обработка выбора кнопки
# ============================
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("lang"):
        _, lang, text = data.split("|")
        context.user_data["language"] = lang
        context.user_data["text"] = text

        # Выбор формата видео
        keyboard = [
            [
                InlineKeyboardButton("Вертикальное 🎥", callback_data="format|vertical"),
                InlineKeyboardButton("Горизонтальное 📺", callback_data="format|horizontal"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите формат видео:", reply_markup=reply_markup)

    elif data.startswith("format"):
        _, orientation = data.split("|")
        vertical = orientation == "vertical"
        lang = context.user_data.get("language", "ru")
        text = context.user_data.get("text", "")

        # 1️⃣ Генерация SEO
        msg = await query.edit_message_text("Генерируем SEO…")
        seo_text = generate_seo(text, language=lang)
        await query.message.reply_text(f"SEO создано:\n{seo_text}")

        # 2️⃣ Генерация изображений с прогрессом
        images = []
        for i in range(3):  # 3 сцены
            await query.message.reply_text(f"Создаём изображение {i+1} из 3…")
            img = generate_image(text)
            images.append(img)

        # 3️⃣ Генерация озвучки
        await query.message.reply_text("Создаём озвучку…")
        voice = generate_voice(text)

        # 4️⃣ Сборка видео
        await query.message.reply_text("Собираем видео…")
        video = generate_video(images, voice, vertical=vertical)

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
