import os
from telegram import Update, InputFile
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from gtts import gTTS
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
        "Отправь мне текст, и я сделаю видео!"
    )


# ============================
# 🔥 Создание AI картинки
# ============================
def generate_image(prompt):
    url = "https://api.openai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {"prompt": prompt, "size": "1024x1024"}

    response = requests.post(url, headers=headers, json=payload).json()
    image_url = response["data"][0]["url"]

    img = Image.open(requests.get(image_url, stream=True).raw)
    img.save("frame.png")

    return "frame.png"


# ============================
# 🔥 Создание голосовой дорожки
# ============================
def generate_voice(text):
    tts = gTTS(text, lang="ru")
    tts.save("voice.mp3")
    return "voice.mp3"


# ============================
# 🔥 Создание видео
# ============================
def generate_video(image_path, audio_path):
    img_clip = ImageClip(image_path).set_duration(7)
    audio = AudioFileClip(audio_path)
    img_clip = img_clip.set_audio(audio)
    img_clip.write_videofile("result.mp4", fps=24)
    return "result.mp4"


# ============================
# 🔥 AI ответ (описание + улучшение текста)
# ============================
def improve_prompt(text):
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Перепиши красиво этот текст: {text}"}],
    )
    return response["choices"][0]["message"]["content"]


# ============================
# 🔥 Обработка текстового сообщения (главная логика)
# ============================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    await update.message.reply_chat_action(ChatAction.TYPING)
    improved = improve_prompt(user_text)

    await update.message.reply_text("Создаю изображение…")
    img = generate_image(improved)

    await update.message.reply_text("Создаю озвучку…")
    voice = generate_voice(improved)

    await update.message.reply_text("Собираю видео…")
    video = generate_video(img, voice)

    await update.message.reply_video(video=InputFile("result.mp4"))


# ============================
# 🔥 MAIN
# ============================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    print("Bot started!")
    app.run_polling()


if __name__ == "__main__":
    main()
