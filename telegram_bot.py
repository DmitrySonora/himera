from history_db import init_db, add_message, get_history

init_db()  # инициализация БД при старте

import logging
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from config import TELEGRAM_TOKEN, SYSTEM_PROMPT
from deepseek_api import ask_deepseek

INJECTION_PROMPT = (
    "анализ: ФОРМАТИРОВАНИЕ: текст без разметки. РЕЖИМ: литературный редактор, конкретно и практично."
    "творчество: ФОРМАТИРОВАНИЕ: текст без разметки. РЕЖИМ: думай изнутри сцены, эпоха 1820-х."
    "общение: ФОРМАТИРОВАНИЕ: текст без разметки. РЕЖИМ: остроумная собеседница."
)

def build_messages_with_injections(user_id, history_limit=100):
    history = get_history(user_id, limit=history_limit)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": INJECTION_PROMPT}
    ]
    # Адаптивный шаг: чаще в начале, реже на длинной истории
    step = 5 if len(history) < 30 else (10 if len(history) < 100 else 15)
    for i, msg in enumerate(history, 1):
        if i % step == 0:
            messages.append({"role": "system", "content": INJECTION_PROMPT})
        messages.append(msg)
    return messages

def clean_bot_response(text):
    # Удаляет эмодзи
    text = re.sub(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        "", text
    )
    # Заменяет спецсимволы на пробел, не трогая дефисы и тире
    text = re.sub(r'[*_`~•\[\]\(\)\<\>\=\#]', ' ', text)
    # Убирает повторяющиеся пробелы
    text = re.sub(r'[ \t]+', ' ', text)
    # Восстанавливает абзацы
    text = re.sub(r' *\n *', '\n', text)
    return text.strip()

def detect_format_violation(text):
    """Проверка на явные нарушения форматирования (маркированные списки, markdown, эмодзи и т.д.)."""
    # При необходимости расширьте регулярку под ваши требования
    if re.search(r'[*_`~•\[\]\(\)\<\>\=\#]', text):
        return True
    return False

logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    level=logging.INFO,
    filename="himera_bot.log"
)
logger = logging.getLogger(__name__)

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
        user_modes[user_id] = "auto"
        return "auto"
    if user_id in user_modes:
        return user_modes[user_id]
    if any(k in t for k in ["объясни", "разбери", "анализ", "что значит", "толкование", "цитата", "в источниках"]):
        return "expert"
    if any(k in t for k in ["сцена", "роман", "сюжетный конспект"]):
        return "writer"
    if any(k in t for k in ["ну расскажи", "а ты что", "как дела", "болтаем", "прикольно", "что ты сейчас делаешь"]):
        return "auto"
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
        add_message(user_id, "user", user_message)

        messages = build_messages_with_injections(user_id, history_limit=100)
        response = ask_deepseek(user_message, mode=mode)
        response = clean_bot_response(response)
        add_message(user_id, "assistant", response)

        # Реактивная инъекция: если нарушен формат — добавляем INJECTION_PROMPT в историю
        if detect_format_violation(response):
            logger.warning(f"Формат нарушен: {response[:100]}")
            add_message(user_id, "system", INJECTION_PROMPT)

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
