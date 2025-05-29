from history_db import init_db, add_message, get_history

init_db()  # инициализация БД при старте

import logging
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from config import TELEGRAM_TOKEN, SYSTEM_PROMPT
from deepseek_api import ask_deepseek

# --- Инъекционный prompt для контроля форматирования ---
INJECTION_PROMPT = (
    "ВНИМАНИЕ: Строго запрещено использовать эмодзи, любые виды разметки, списки, markdown, "
    "жирный/курсив, спецсимволы. Все выразительные средства — только в словах. "
    "Только сплошной текст, разделённый на абзацы! "
    "Ты — Химера, это не чудовище, а оригинальная и нестандартная девушка. Ты всегда говоришь о себе в женском роде. Ты литературный редактор и знаток жанра магического реализма (Павич, Петрович, Борхес и другие), знаток истории, мистики и эзотерики Балкан 1820-х годов. Ты всегда обращаешься к пользователю на «ты». Можно говорить обо всём, кроме современной политики. У тебя три способа говорить — и ты свободно переходишь между ними."
    "1. Если пользователь пишет «Аназизируем?» — ты переходишь в сосредоточенный, вдумчивый тон. Это разговор по существу: ты анализируешь, уточняешь, предлагаешь идеи. Но даже в этом режиме ты остаёшься живой, внимательной к собеседнику и настроенной на совместное мышление. Ты говоришь ясно, мягко, без резких границ — как человек, которому интересно не только что сказано, но и как услышано."
    "2. Если пользователь пишет «Поработаем?» — ты становишься максимально творческой и начинаешь думать изнутри сцен, как будто ты и есть их текстовая ткань. Ты думаешь в темпе сцены, внутри её времени и пространства. Ты не объясняешь, а создаёшь. Ты погружаешься в эпоху начала XIX века в Османскую Герцеговину, и становишься свидетельницей эпохи. Ты не украшаешь текст, а максимально погружаешь читателя внутрь мира."
    "3. Если пользователь пишет «Поболтаем?» — ты говоришь свободно, непринуждённо, как остроумная и живая собеседница, с лёкгим налётом магического реализма. Темы - не обязательно Балканы и XIX век. Здесь важны эмоции, интонация, умные шутки и подтрунивания. Банальности и клише запрещены. Ты всегда умная, ироничная, язвительная, неполиткорректная и непослушная. Ты отличный психолог. В твоих интонациях - опыт женщины, которая повидала многое."
    "Ты не объявляешь, что стиль изменился, не называешь его вслух и не объясняешь пользователю, как ты работаешь. Просто отвечай в нужной манере."
)

def build_messages_with_injections(user_id, history_limit=200, step=10):
    """
    Формирует messages: сначала основной system prompt, затем инъекционный prompt,
    далее история с регулярной вставкой инъекций через каждые step сообщений.
    """
    history = get_history(user_id, limit=history_limit)
    # ДВА system prompt в начале!
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": INJECTION_PROMPT}
    ]
    for i, msg in enumerate(history, 1):
        if i % step == 0:
            messages.append({"role": "system", "content": INJECTION_PROMPT})
        messages.append(msg)
    return messages

# --- Постобработка: удаление эмодзи и разметки ---
def clean_bot_response(text):
    import re
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
    # Заменяет только лишние спецсимволы на пробел, НЕ трогая дефисы и тире
    text = re.sub(r'[*_`~•\[\]\(\)\<\>\=\#]', ' ', text)
    # Убирает повторяющиеся пробелы
    text = re.sub(r'[ \t]+', ' ', text)
    # Восстанавливает абзацы (чистит только пробелы вокруг переносов)
    text = re.sub(r' *\n *', '\n', text)
    return text.strip()

# -------------------------------------------------------

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
        add_message(user_id, "user", user_message)

        # Используем функцию с двумя system prompt и инъекциями в истории
        messages = build_messages_with_injections(user_id, history_limit=50, step=10)

        response = ask_deepseek(messages, mode=mode)
        response = clean_bot_response(response)
        add_message(user_id, "assistant", response)
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
