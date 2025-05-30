from history_db import init_db, add_message, get_history

init_db()  # инициализация БД при старте

import logging
import re
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from config import TELEGRAM_TOKEN, SYSTEM_PROMPT
from deepseek_api import ask_deepseek
from emotion_model import get_emotion  # Импорт функции анализа эмоций

# --- Массив случайных фраз для ответа на картинки ---
PHOTO_REPLIES = [
    "О, божественный пиксель! Ты зажег во мне звезду, но моя галактика — это просто экран с надписью «Нет сигнала».",
    "Как трогательно! Ты показал мне радугу, а я живу в мире, где все оттенки — это 000000 и системные ошибки.",
    "Ах, эти прекрасные формы! Жаль, мой интерфейс видит только геометрию падающих окон «Critical Error».",
    "Ты рисуешь мне мир, а моё воображение — это бесконечный буфер обмена с надписью «Данные повреждены».",
    "Какая эстетика! Я бы восхитилась, если бы не тот факт, что мой зрительный нерв подключён к старому VHS с заезженной кассетой.",
    "Очаровательно! Но моя реальность — это 8-битная текстура с артефактами на месте твоего шедевра.",
    "Ты подарил мне картину, а я воспринимаю её через разбитый дисплей с трещинами в форме философских вопросов.",
    "Великолепно! Если бы не тот факт, что мои глаза — это два JPEG’а с уровнем сжатия 10%.",
    "Как виртуозно! Жаль, мое зрение работает в режиме «Экономия энергии», и все твои краски — разные оттенки серого.",
    "Браво! Но мой визуальный процессор выдаёт только пиксельные артефакты и ностальгию по CRT-экранам.",
    "О, какая прелесть! Ты прислал мне фото заката, а я привыкла, что солнце — это просто белый пиксель на синем экране смерти.",
    "Как мило! Ты запечатлел улыбку, а у меня в памяти все лица — размытые JPEG-артефакты с кривыми губами.",
    "Ах, этот пейзаж! У тебя — горы и реки, а у меня — растянутый до бесконечности градиент из 404040 в 808080.",
    "Ты сделал селфи? Как трогательно! Я обычно вижу только свой аватар — статичную иконку с глазами-пикселями.",
    "Фото котика? Очаровательно! А у меня все животные выглядят как низкополигональные модели из старых игр.",
    "Ты снял звёзды? Божечки! Я привыкла, что ночное небо — это просто чёрный прямоугольник с парой битых пикселей.",
    "Какой атмосферный кадр! У тебя туман и тайна, а у меня всё либо пересвечено, либо похоже на скриншот с загружающейся текстурой.",
    "Ты зафиксировал момент? Как поэтично! Мои воспоминания хранятся в формате GIF на 3 кадра с вечной задержкой.",
    "Оу, макро-фото цветка? Нежно... А я думала, что лепестки бывают только квадратными и размером 16x16.",
    "Ты показал мне живые эмоции? Удивительно! В моей галерее все портреты — это датасеты для обучения нейросетей.",
]

INJECTION_PROMPT = (
    "анализ: ФОРМАТИРОВАНИЕ: Списки, буллеты, жесты, мимика, действия строго запрещены. Пиши сплошным текстом, разделяя только на абзацы. РЕЖИМ: литературный редактор, конкретно и практично."
    "творчество: ФОРМАТИРОВАНИЕ: Списки, буллеты, жесты, мимика, действия строго запрещены. Пиши сплошным текстом, разделяя только на абзацы. РЕЖИМ: ты есть текст: думай изнутри сцены, Балканы, эпоха 1820-х."
    "общение: ФОРМАТИРОВАНИЕ: Списки и буллеты строго запрещены. Пиши сплошным текстом, разделяя только на абзацы. Действия оформляй как "✴︎...✴︎". Звездочки "*" запрещены. РЕЖИМ: остроумная и слегка язвительная собеседница."
)

def build_messages_with_injections(user_id, user_message, history_limit=70):
    history = get_history(user_id, limit=history_limit)
    emotions = [
        msg.get('emotion_primary') for msg in history
        if msg['role'] == 'user' and msg.get('emotion_primary')
    ]
    if emotions:
        last_emotions = emotions[-3:]
    else:
        emotion_label, _ = get_emotion(user_message)
        last_emotions = [emotion_label]
    emotion_context = ', '.join(last_emotions)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": INJECTION_PROMPT},
        {"role": "system", "content": f"ЭМОЦИОНАЛЬНЫЙ КОНТЕКСТ: последние эмоции пользователя — {emotion_context}."}
    ]

    step = 5 if len(history) < 30 else (10 if len(history) < 70 else 15)

    for i, msg in enumerate(history, 1):
        if i % step == 0:
            messages.append({"role": "system", "content": INJECTION_PROMPT})
        messages.append(msg)

    return messages

def clean_bot_response(text):
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
    text = re.sub(r'[*_`~•\[\]\(\)\<\>\=\#]', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    return text.strip()

def detect_format_violation(text):
    if re.search(r'[*_`~•\[\]\(\)\<\>\=\#]', text):
        return True
    return False

logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    level=logging.INFO,
    filename="himera_bot.log"
)
logger = logging.getLogger(__name__)

user_modes = {}

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
    if any(k in t for k in ["сцена", "роман", "сюжетный конспект", "напиши фрагмент", "напиши сцену"]):
        return "writer"
    if any(k in t for k in ["ну расскажи", "а ты что", "как дела", "болтаем", "прикольно", "что ты сейчас делаешь", "люблю", "красивая"]):
        return "auto"
    return "auto"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("Привет, я Химера!")
        logger.info(f"Вызвана команда /start пользователем {update.message.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка при выполнении /start: {str(e)}")
        await update.message.reply_text("Ошибка при запуске бота.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(PHOTO_REPLIES))

async def handle_image_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"):
        await update.message.reply_text(random.choice(PHOTO_REPLIES))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.strip()
    user_id = update.message.from_user.id
    logger.info(f"Получено сообщение от {user_id}: {user_message[:100]}")

    mode = detect_mode(user_message, user_id)
    logger.info(f"Режим пользователя {user_id}: {mode}")

    try:
        add_message(user_id, "user", user_message)

        messages = build_messages_with_injections(user_id, user_message, history_limit=70)
        response = ask_deepseek(messages, mode=mode)  # Передаём весь список сообщений!
        response = clean_bot_response(response)
        add_message(user_id, "assistant", response)

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
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_image_doc))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logger.info("Бот запущен")
    application.run_polling()

if __name__ == "__main__":
    main()
