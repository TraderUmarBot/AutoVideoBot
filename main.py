import logging
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Таймфреймы и пары
TIMEFRAMES = ["3s", "10s", "15s", "30s", "1m"]
PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD"]

# Функция генерации сигнала
def generate_signal():
    return random.choice(["CALL 📈", "PUT 📉"])

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(pair, callback_data=pair)] for pair in PAIRS
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привет! Выберите валютную пару или актив для сигнала:", reply_markup=reply_markup
    )

# Обработка нажатия на кнопку пары
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Создаем клавиатуру для таймфреймов
    keyboard = [
        [InlineKeyboardButton(tf, callback_data=f"{query.data}|{tf}")] for tf in TIMEFRAMES
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=f"Выбрана пара: {query.data}\nВыберите таймфрейм:", reply_markup=reply_markup
    )

# Генерация сигнала
async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    pair, tf = query.data.split("|")
    signal = generate_signal()
    
    await query.edit_message_text(
        text=f"Сигнал для {pair} на {tf}:\n\n{signal}\n\n⚠️ Напоминаем: это тестовый сигнал, используйте на демо-счете!"
    )

# Основная функция запуска бота
if __name__ == "__main__":
    TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # <-- Вставь сюда токен вашего бота
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(signal, pattern=r"^\w+\/\w+\|"))
    app.add_handler(CallbackQueryHandler(button, pattern=r"^\w+\/\w+$"))
    
    print("Бот запущен...")
    app.run_polling()
