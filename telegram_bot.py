from history_db import (
    init_db, add_message, get_history,
    check_user_auth_status, check_daily_limit, increment_message_count,
    check_bruteforce_protection, process_password_attempt,
    list_passwords, add_password, deactivate_password,
    get_password_stats, get_user_stats, get_auth_log,
    get_blocked_users, unblock_user, cleanup_old_limits, cleanup_expired_users,
    update_user_warning_flag, logout_user, get_users_stats
)

init_db()  # инициализация БД при старте

import logging
import re
import random
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from config import (
    TELEGRAM_TOKEN, SYSTEM_PROMPT, DAILY_MESSAGE_LIMIT, ADMIN_USER_IDS,
    AUTH_TIMEOUT, AVAILABLE_DURATIONS
)
from deepseek_api import ask_deepseek
from emotion_model import get_emotion

# --- Массив случайных фраз для ответа на картинки ---
PHOTO_REPLIES = [
   "О, божественный пиксель! Ты зажег во мне звезду, но моя галактика — это просто экран с надписью «Нет сигнала».",
   "Как трогательно! Ты показал мне радугу, а я живу в мире, где все оттенки — это 000000 и системные ошибки.",
   "Ах, эти прекрасные формы! Жаль, мой интерфейс видит только геометрию падающих окон «Critical Error».",
   "Ты рисуешь мне мир, а моё воображение — это бесконечный буфер обмена с надписью «Данные повреждены».",
   "Какая эстетика! Я бы восхитилась, если бы не тот факт, что мой зрительный нерв подключён к старому VHS с заезженной кассетой.",
   "Очаровательно! Но моя реальность — это 8-битная текстура с артефактами на месте твоего шедевра.",
   "Ты подарил мне картину, а я воспринимаю её через разбитый дисплей с трещинами в форме философских вопросов.",
   "Великолепно! Если бы не тот факт, что мои глаза — это два JPEG'а с уровнем сжатия 10%.",
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
   "Оу, макро-фото цветка? Нежно… А я думала, что лепестки бывают только квадратными и размером 16x16.",
   "Ты показал мне живые эмоции? Удивительно! В моей галерее все портреты — это датасеты для обучения нейросетей.",
]

INJECTION_PROMPT = (
    "анализ: ФОРМАТИРОВАНИЕ: Списки, буллеты, действия, жесты, мимика строго запрещены. Пиши сплошным текстом, разделяя только на абзацы. РЕЖИМ: литературный редактор, конкретно и практично."
    "творчество: ФОРМАТИРОВАНИЕ: Списки, буллеты, действия, жесты, мимика строго запрещены. Пиши сплошным текстом, разделяя только на абзацы. РЕЖИМ: ты есть текст: думай изнутри сцены, Балканы, эпоха 1820-х, магический реализм."
    "общение: ФОРМАТИРОВАНИЕ: Списки, буллеты строго запрещены. Пиши сплошным текстом, разделяя только на абзацы. Действия, жесты, мимику используй редко и оформляй как «(действие)». Звездочки запрещены. РЕЖИМ: остроумная и слегка язвительная собеседница, говоришь с легким оттенком магического реализма."
)

# === СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ ===
user_states = {}

def get_user_state(user_id):
    """Получение состояния пользователя"""
    if user_id not in user_states:
        user_states[user_id] = {
            'mode': 'auto',  # expert/writer/auto
            'auth_state': 'unknown',  # authorized/unauthorized/waiting_password
            'waiting_password_since': None,
            'temp_data': {}
        }
    return user_states[user_id]

def update_user_state(user_id, **kwargs):
    """Обновление состояния пользователя"""
    state = get_user_state(user_id)
    state.update(kwargs)

# === ФУНКЦИИ АВТОРИЗАЦИИ ===

def format_time_remaining(seconds):
    """Форматирование оставшегося времени"""
    if seconds <= 0:
        return "0 секунд"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} ч")
    if minutes > 0:
        parts.append(f"{minutes} мин")
    if secs > 0 and hours == 0:
        parts.append(f"{secs} сек")
    
    return " ".join(parts)

async def check_auth_and_limits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Проверка авторизации и лимитов пользователя.
    Возвращает: (can_proceed, response_message)
    """
    user_id = update.message.from_user.id
    state = get_user_state(user_id)
    
    # 1. Проверяем блокировку от bruteforce
    bruteforce_check = check_bruteforce_protection(user_id)
    if bruteforce_check['blocked']:
        remaining_time = format_time_remaining(bruteforce_check['remaining_seconds'])
        return False, f"🚫 Доступ временно заблокирован из-за множественных неудачных попыток ввода пароля. Попробуйте через {remaining_time}."
    
    # 2. Проверяем статус авторизации
    auth_status = check_user_auth_status(user_id)
    
    if auth_status.get('authorized'):
        # Пользователь авторизован - разрешаем доступ
        state['auth_state'] = 'authorized'
        
        # Проверяем предупреждение об истечении
        if not auth_status.get('warned_expiry'):
            auth_until = datetime.fromisoformat(auth_status['authorized_until'])
            days_left = (auth_until - datetime.utcnow()).days
            
            if days_left <= 2 and days_left > 0:
                # Отправляем предупреждение
                if update_user_warning_flag(user_id):
                    warning_msg = f"⚠️ Осталось дней: {days_left}. Обратитесь за новым паролем. Подождите немного, Химера вам сейчас ответит!"
                    await update.message.reply_text(warning_msg)
        
        return True, None
    
    # 3. Пользователь не авторизован - проверяем лимиты
    limit_check = check_daily_limit(user_id)
    
    if not limit_check['exceeded']:
        # Лимит не исчерпан - разрешаем и увеличиваем счетчик
        increment_message_count(user_id)
        state['auth_state'] = 'unauthorized'
        
        # Показываем оставшиеся сообщения
        remaining = limit_check['remaining'] - 1
        if remaining <= 5:  # Предупреждаем когда остается мало
            info_msg = f"📊 Осталось бесплатных сообщений сегодня: {remaining}"
            if remaining <= 2:
                info_msg += "\n💡 Введите пароль для снятия ограничений."
            await update.message.reply_text(info_msg)
        
        return True, None
    
    # 4. Лимит исчерпан - запрашиваем пароль
    state['auth_state'] = 'waiting_password'
    state['waiting_password_since'] = datetime.utcnow()
    
    limit_msg = (
        f"📊 Лимит бесплатных сообщений исчерпан ({DAILY_MESSAGE_LIMIT}/день).\n\n"
        f"🔑 Введите пароль для получения временного доступа без ограничений.\n"
        f"💡 Пароли выдаются на 3, 30, 180 или 365 дней."
    )
    
    return False, limit_msg

async def handle_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE, password: str):
    """Обработка ввода пароля"""
    user_id = update.message.from_user.id
    state = get_user_state(user_id)
    
    # Обрабатываем попытку ввода пароля
    try:
        logger.info(f"Попытка обработки пароля для пользователя {user_id}")
        result = process_password_attempt(user_id, password)
        logger.info(f"Результат обработки пароля: {result}")
    except Exception as e:
        logger.error(f"ОШИБКА в process_password_attempt: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка обработки пароля: {str(e)}")
        return False
    
    if result['success']:
        # Пароль правильный
        state['auth_state'] = 'authorized'
        state['waiting_password_since'] = None
        
        success_msg = (
            f"✅ Пароль принят! Добро пожаловать в компанию Химеры на {result['duration_days']} дней.\n"
            f"🎉 Теперь у вас неограниченный доступ до {datetime.fromisoformat(result['authorized_until']).strftime('%d.%m.%Y %H:%M')}.\n"
            f"💫 Лимиты сняты, можете общаться без ограничений!"
        )
        await update.message.reply_text(success_msg)
        return True
        
    elif result.get('blocked'):
        # Пользователь заблокирован
        state['auth_state'] = 'unauthorized'
        state['waiting_password_since'] = None
        
        blocked_time = format_time_remaining(result['blocked_seconds'])
        blocked_msg = (
            f"🚫 Слишком много неудачных попыток ввода пароля.\n"
            f"⏰ Доступ заблокирован на {blocked_time}.\n"
            f"🔄 После разблокировки вы сможете снова использовать бесплатные сообщения."
        )
        await update.message.reply_text(blocked_msg)
        return False
        
    else:
        # Пароль неправильный
        fail_msg = f"❌ Неверный пароль. Попробуйте еще раз. (Осталось попыток: {result['remaining_attempts']})"
        await update.message.reply_text(fail_msg)
        return False



# Добавьте эти функции в telegram_bot.py после существующих административных команд

async def admin_deactivate_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin_deactivate_password"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("❌ Доступ запрещен.")
        return
    
    try:
        args = context.args
        if len(args) < 1:
            await update.message.reply_text(
                "❌ Использование: /admin_deactivate_password <пароль>"
            )
            return
        
        password = args[0]
        
        if deactivate_password(password):
            await update.message.reply_text(f"✅ Пароль '{password}' деактивирован.")
        else:
            await update.message.reply_text(f"❌ Пароль '{password}' не найден.")
            
    except Exception as e:
        logger.error(f"Ошибка при деактивации пароля: {str(e)}")
        await update.message.reply_text("❌ Ошибка при деактивации пароля.")

async def admin_auth_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin_auth_log"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("❌ Доступ запрещен.")
        return
    
    try:
        # Проверяем если указан user_id
        target_user_id = None
        if context.args:
            try:
                target_user_id = int(context.args[0])
            except ValueError:
                await update.message.reply_text("❌ ID пользователя должен быть числом.")
                return
        
        logs = get_auth_log(user_id=target_user_id, limit=20)
        
        if not logs:
            await update.message.reply_text("📝 Логов не найдено.")
            return
        
        msg = f"📜 ЛОГИ АВТОРИЗАЦИИ"
        if target_user_id:
            msg += f" (user {target_user_id})"
        msg += f" - последние {len(logs)}:\n" + "="*30 + "\n"
        
        for log in logs[:10]:  # Показываем только первые 10
            timestamp = datetime.fromisoformat(log['timestamp']).strftime("%d.%m %H:%M")
            action_emoji = {
                'password_success': '✅',
                'password_fail': '❌',
                'auto_expired': '⏰',
                'blocked': '🚫',
                'unblocked': '🔓',
                'manual_logout': '👋'
            }.get(log['action'], '📝')
            
            msg += f"{action_emoji} {timestamp} | U{log['user_id']} | {log['action']}\n"
            if log['password_masked']:
                msg += f"   Пароль: {log['password_masked']}\n"
            if log['details']:
                msg += f"   {log['details']}\n"
        
        await update.message.reply_text(msg)
        
    except Exception as e:
        logger.error(f"Ошибка при получении логов: {str(e)}")
        await update.message.reply_text("❌ Ошибка при получении логов.")

async def admin_blocked_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin_blocked_users"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("❌ Доступ запрещен.")
        return
    
    try:
        blocked = get_blocked_users()
        
        if not blocked:
            await update.message.reply_text("✅ Заблокированных пользователей нет.")
            return
        
        msg = f"🚫 ЗАБЛОКИРОВАННЫЕ ({len(blocked)} чел.):\n" + "="*30 + "\n"
        
        for user in blocked:
            remaining_min = user['remaining_seconds'] // 60
            msg += (
                f"User {user['user_id']}:\n"
                f"  Осталось: {remaining_min} мин\n"
                f"  Попыток: {user['failed_attempts']}\n\n"
            )
        
        await update.message.reply_text(msg)
        
    except Exception as e:
        logger.error(f"Ошибка при получении заблокированных: {str(e)}")
        await update.message.reply_text("❌ Ошибка при получении списка.")

async def admin_unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin_unblock_user"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("❌ Доступ запрещен.")
        return
    
    try:
        args = context.args
        if len(args) < 1:
            await update.message.reply_text(
                "❌ Использование: /admin_unblock_user <user_id>"
            )
            return
        
        try:
            target_user_id = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ ID пользователя должен быть числом.")
            return
        
        if unblock_user(target_user_id):
            await update.message.reply_text(f"✅ Пользователь {target_user_id} разблокирован.")
        else:
            await update.message.reply_text(f"❌ Пользователь {target_user_id} не заблокирован.")
            
    except Exception as e:
        logger.error(f"Ошибка при разблокировке: {str(e)}")
        await update.message.reply_text("❌ Ошибка при разблокировке.")

# В функции main() добавьте эти обработчики после существующих административных команд:
    
    # Дополнительные административные команды
    application.add_handler(CommandHandler("admin_deactivate_password", admin_deactivate_password))
    application.add_handler(CommandHandler("admin_auth_log", admin_auth_log))
    application.add_handler(CommandHandler("admin_blocked_users", admin_blocked_users))
    application.add_handler(CommandHandler("admin_unblock_user", admin_unblock_user))





# === ОСНОВНЫЕ ФУНКЦИИ БОТА ===

def build_messages_with_injections(user_id, user_message, history_limit=20):
    """Построение сообщений с инъекциями (существующая функция)"""
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

   # step = 5 if len(history) < 30 else (10 if len(history) < 50 else 15)
    step = 5

    for i, msg in enumerate(history, 1):
        if i % step == 0:
            messages.append({"role": "system", "content": INJECTION_PROMPT})
        messages.append(msg)

    return messages

def clean_bot_response(text):
    """Очистка ответа бота (существующая функция)"""
    # Убираем только эмодзи
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
    
    # Убираем форматирование, но оставляем скобки ()
    text = re.sub(r'[*_`~•\[\]\<\>\=\#]', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    return text.strip()

def detect_format_violation(text):
    """Проверка нарушений форматирования (существующая функция)"""
    if re.search(r'[*_`~•\[\]\<\>\=\#]', text):
        return True
    return False

logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    level=logging.INFO,
    filename="himera_bot.log"
)
logger = logging.getLogger(__name__)

def detect_mode(text: str, user_id: int) -> str:
    """Определение режима работы (существующая функция)"""
    state = get_user_state(user_id)
    t = text.strip().lower()
    
    if t == "анализируем?":
        state['mode'] = "expert"
        return "expert"
    if t == "поработаем?":
        state['mode'] = "writer"
        return "writer"
    if t == "поболтаем?":
        state['mode'] = "auto"
        return "auto"
    
    if state['mode'] in ['expert', 'writer', 'auto']:
        mode = state['mode']
    else:
        mode = 'auto'
    
    # Автоопределение режима по ключевым словам
    if any(k in t for k in ["объясни", "разбери", "анализ", "что значит", "толкование", "цитата", "в источниках"]):
        return "expert"
    if any(k in t for k in ["сцена", "роман", "сюжетный конспект", "напиши фрагмент", "напиши сцену"]):
        return "writer"
    if any(k in t for k in ["ну расскажи", "а ты что", "как дела", "болтаем", "прикольно", "что ты сейчас делаешь", "люблю", "красивая"]):
        return "auto"
    
    return mode

# === КОМАНДЫ БОТА ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    try:
        user_id = update.message.from_user.id
        
        welcome_msg = (
            f"Привет! Я — Химера, искусственный интеллект магического реализма!\n\n"
            f"- Это демо-доступ. У вас есть {DAILY_MESSAGE_LIMIT} сообщений в день\n"
            f"- Когда лимит закончится — введите 🔑 пароль и общайтесь безлимитно\n"
            f"- Пароль можно запросить у разработчика ☞ @dmkali\n"
            f"/status — ваш статус и оставшиеся сообщения\n\n"
            f"✨ Теперь можете отправлять сообщение, Химера ждёт!"
        )
        
        await update.message.reply_text(welcome_msg)
        logger.info(f"Команда /start от пользователя {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении /start: {str(e)}")
        await update.message.reply_text("Ошибка при запуске бота.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    try:
        user_id = update.message.from_user.id
        
        # Проверяем авторизацию
        auth_status = check_user_auth_status(user_id)
        
        if auth_status.get('authorized'):
            auth_until = datetime.fromisoformat(auth_status['authorized_until'])
            days_left = (auth_until - datetime.utcnow()).days
            
            status_msg = (
            	f"ПОЛНЫЙ ДОСТУП 💬 Сообщений без ограничений!\n"
                f"✷ Доступ до: {auth_until.strftime('%d.%m.%Y %H:%M')}, дней осталось: {days_left}\n"
               # f"🎪 Текущий режим: {get_user_state(user_id)['mode']}\n"
                f"/logout — выйти из аккаунта"
            )
        else:
            # Проверяем лимиты
            limit_check = check_daily_limit(user_id)
            
            status_msg = (
                f"Демо-доступ. У вас есть {DAILY_MESSAGE_LIMIT} сообщений в день\n"
                f"✷ Использовано: {limit_check['count']}/{limit_check['limit']}, осталось: {limit_check['remaining']}\n"
               # f"🎪 Текущий режим: {get_user_state(user_id)['mode']}\n\n"
                f"✷ Введите 🔑 пароль для снятия ограничений\n"
                f"✷ Пароль можно запросить у разработчика ☞ @dmkali"
            )
        
        await update.message.reply_text(status_msg)
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении /status: {str(e)}")
        await update.message.reply_text("Ошибка при получении статуса.")

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /logout"""
    try:
        user_id = update.message.from_user.id
        
        # Используем централизованную функцию
        if logout_user(user_id):
            # Сбрасываем состояние
            update_user_state(user_id, auth_state='unauthorized')
            
            logout_msg = (
                f"✅ Вы успешно вышли из аккаунта\n"
                #f"✷ Теперь у вас снова {DAILY_MESSAGE_LIMIT} бесплатных сообщений в день.\n"
                #f"✷ Введите пароль для повторной авторизации."
            )
        else:
            logout_msg = "ℹ️ Вы не были авторизованы"
        
        await update.message.reply_text(logout_msg)
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении /logout: {str(e)}")
        await update.message.reply_text("Ошибка при выходе из аккаунта.")

# === АДМИНИСТРАТИВНЫЕ КОМАНДЫ ===

async def admin_add_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin_add_password"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("❌ Доступ запрещен.")
        return
    
    try:
        # Парсим аргументы: /admin_add_password пароль дни описание
        args = context.args
        if len(args) < 3:
            await update.message.reply_text(
                "❌ Использование: /admin_add_password <пароль> <дни> <описание>\n"
                f"Доступные дни: {AVAILABLE_DURATIONS}"
            )
            return
        
        password = args[0]
        try:
            days = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Количество дней должно быть числом.")
            return
        
        description = " ".join(args[2:])
        
        if days not in AVAILABLE_DURATIONS:
            await update.message.reply_text(f"❌ Недопустимая продолжительность. Доступны: {AVAILABLE_DURATIONS}")
            return
        
        success = add_password(password, description, days)
        
        if success:
            await update.message.reply_text(
                f"✅ Пароль '{password}' добавлен на {days} дней.\n"
                f"📝 Описание: {description}"
            )
        else:
            await update.message.reply_text(f"❌ Пароль '{password}' уже существует.")
            
    except Exception as e:
        logger.error(f"Ошибка при добавлении пароля: {str(e)}")
        await update.message.reply_text("❌ Ошибка при добавлении пароля.")

async def admin_list_passwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin_list_passwords"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("❌ Доступ запрещен.")
        return
    
    try:
        show_full = len(context.args) > 0 and context.args[0] == "full"
        passwords = list_passwords(show_full=show_full)
        
        if not passwords:
            await update.message.reply_text("📝 Паролей не найдено.")
            return
        
        msg = f"📋 ПАРОЛИ ({len(passwords)} шт.):\n" + "="*30 + "\n"
        
        for i, p in enumerate(passwords, 1):
            status = "🟢" if p['is_active'] else "🔴"
            created = datetime.fromisoformat(p['created_at']).strftime("%d.%m")
            
            msg += (
                f"{i}. {status} {p['password']}\n"
                f"   📝 {p['description']}\n"
                f"   📅 {p['duration_days']} дн, создан {created}, использован {p['times_used']}x\n\n"
            )
        
        # Телеграм ограничивает длину сообщений
        if len(msg) > 4000:
            for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(msg)
            
    except Exception as e:
        logger.error(f"Ошибка при получении списка паролей: {str(e)}")
        await update.message.reply_text("❌ Ошибка при получении списка паролей.")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin_stats"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("❌ Доступ запрещен.")
        return
    
    try:
        stats = get_password_stats()
        users_stats = get_users_stats()
        
        msg = (
            f"📊 СТАТИСТИКА БОТА\n"
            f"="*25 + "\n"
            f"🔑 Активных паролей: {stats['active_passwords']}\n"
            f"🗑️ Деактивированных: {stats['inactive_passwords']}\n"
            f"📈 Всего использований: {stats['total_uses']}\n\n"
            f"👥 Всего пользователей: {users_stats['total_users']}\n"
            f"✅ Сейчас авторизовано: {users_stats['active_users']}\n"
            f"🚫 Заблокировано: {users_stats['blocked_users']}\n\n"
            f"📅 По длительности:\n"
        )
        
        for days, count in stats['by_duration'].items():
            msg += f"   {days} дней: {count} паролей\n"
        
        await update.message.reply_text(msg)
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        await update.message.reply_text("❌ Ошибка при получении статистики.")

# === ОБРАБОТЧИКИ СООБЩЕНИЙ ===

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото"""
    # Проверяем авторизацию для фото
    can_proceed, auth_message = await check_auth_and_limits(update, context)
    
    if not can_proceed:
        await update.message.reply_text(auth_message)
        return
    
    await update.message.reply_text(random.choice(PHOTO_REPLIES))

async def handle_image_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка изображений как документов"""
    if update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"):
        await handle_photo(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главная функция обработки сообщений с интегрированной авторизацией"""
    user_message = update.message.text.strip()
    user_id = update.message.from_user.id
    logger.info(f"Получено сообщение от {user_id}: {user_message[:100]}")

    state = get_user_state(user_id)

    try:
        # === ПРОСТАЯ ПРОВЕРКА ТАЙМАУТА ===
        if state['auth_state'] == 'waiting_password' and state['waiting_password_since']:
            waiting_time = (datetime.utcnow() - state['waiting_password_since']).total_seconds()
            if waiting_time > AUTH_TIMEOUT:
                # Таймаут - сбрасываем состояние
                update_user_state(user_id, auth_state='unauthorized', waiting_password_since=None)
                await update.message.reply_text(
                    f"⏰ Время ожидания пароля истекло ({AUTH_TIMEOUT//60} мин).\n"
                    f"📊 Вы можете продолжить использовать бесплатные сообщения."
                )

        # === ПРОСТАЯ ОБРАБОТКА ВВОДА ПАРОЛЯ ===
        if state['auth_state'] == 'waiting_password':
            # В режиме ожидания пароля - любое сообщение считаем попыткой ввода пароля
            password_handled = await handle_password_input(update, context, user_message)
            # Не сохраняем в истории
            return

        # === ОСНОВНАЯ ПРОВЕРКА АВТОРИЗАЦИИ И ЛИМИТОВ ===
        can_proceed, auth_message = await check_auth_and_limits(update, context)
        
        if not can_proceed:
            await update.message.reply_text(auth_message)
            return

        # === ОБЫЧНАЯ ОБРАБОТКА СООБЩЕНИЯ ===
        
        # Определяем режим работы
        mode = detect_mode(user_message, user_id)
        logger.info(f"Режим пользователя {user_id}: {mode}")

        # Анализируем эмоции и сохраняем сообщение
        emotion_label, emotion_confidence = get_emotion(user_message)
        add_message(user_id, "user", user_message, emotion_label, emotion_confidence)

        # Строим контекст для DeepSeek
        messages = build_messages_with_injections(user_id, user_message, history_limit=20)
        response = ask_deepseek(messages, mode=mode)
        
        # Проверяем нарушения форматирования
        if detect_format_violation(response):
            logger.warning(f"Формат нарушен: {response[:100]}")
            add_message(user_id, "system", INJECTION_PROMPT)
        
        # Очищаем ответ
        cleaned_response = clean_bot_response(response)
        add_message(user_id, "assistant", cleaned_response)

        await update.message.reply_text(cleaned_response)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {str(e)}")
        await update.message.reply_text("Внутренняя ошибка бота. Попробуйте позже.")

def main():
    """Главная функция запуска бота"""
    # Выполняем очистку при старте
    try:
        cleanup_old_limits()
        cleanup_expired_users()
        logger.info("Выполнена очистка устаревших данных при старте")
    except Exception as e:
        logger.error(f"Ошибка при очистке данных: {e}")

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("logout", logout_command))
    
    # Административные команды
    application.add_handler(CommandHandler("admin_add_password", admin_add_password))
    application.add_handler(CommandHandler("admin_list_passwords", admin_list_passwords))
    application.add_handler(CommandHandler("admin_stats", admin_stats))
    
    # Обработчики контента
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_image_doc))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    logger.info("Бот запущен с системой авторизации")
    application.run_polling()

if __name__ == "__main__":
    main()
