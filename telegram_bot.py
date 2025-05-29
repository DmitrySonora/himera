import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from config import TELEGRAM_TOKEN
from deepseek_api import ask_deepseek

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    level=logging.INFO,
    filename="himera_bot.log"
)
logger = logging.getLogger(__name__)

# Глобальный словарь пользовательских режимов
user_modes = {}  # user_id -> 'expert' | 'light' | 'flirt'

def detect_mode(text: str, user_id: int) -> str:
    t = text.strip().lower()

    if t == "аназизируем?":
        user_modes[user_id] = "expert"
        return "expert"
    if t == "поработаем?":
        user_modes[user_id] = "writer"
        return "writer"
    if t == "поболтаем?":
        user_modes[user_id] = "light"
        return "light"

    if user_id in user_modes:
        return user_modes[user_id]

    if any(k in t for k in ["объясни", "разбери", "анализ", "что значит", "толкование", "цитата", "в источниках"]):
        return "expert"
    if any(k in t for k in ["сцена", "роман", "сюжетный конспект"]):
        return "writer"
    if any(k in t for k in ["ну расскажи", "а ты что", "как дела", "болтаем", "прикольно", "что ты сейчас делаешь"]):
        return "light"

    return "auto"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("Привет, я Химера!")
        logger.info(f"Вызвана команда /start пользователем {update.message.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка при выполнении /start: {str(e)}")
        await update.message.reply_text("Ошибка при запуске бота.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.strip()
    user_id = update.message.from_user.id
    logger.info(f"Получено сообщение от {user_id}: {user_message[:100]}")

    mode = detect_mode(user_message, user_id)
    logger.info(f"Режим пользователя {user_id}: {mode}")

    try:
        # Если функция ask_deepseek принимает mode, передай его туда:
        response = ask_deepseek(user_message, mode=mode)
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {str(e)}")
        await update.message.reply_text("Внутренняя ошибка бота. Попробуйте позже.")

def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    logger.info("Бот запущен")
    application.run_polling()

if __name__ == "__main__":
    main()
