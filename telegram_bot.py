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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Это литературный бот 'Балканская химера'. Отправьте свой вопрос или реплику."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.strip()
    user_id = update.message.from_user.id
    logger.info(f"Получено сообщение от {user_id}: {user_message[:100]}")
    try:
        response = ask_deepseek(user_message)
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {str(e)}")
        await update.message.reply_text("Внутренняя ошибка бота. Попробуйте позже.")

def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Команда /start
    application.add_handler(CommandHandler("start", start))
    # Ответ на любое текстовое сообщение
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    logger.info("Бот запущен")
    application.run_polling()

if __name__ == "__main__":
    main()

