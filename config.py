import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла (если он присутствует)
load_dotenv()

# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7404854015:AAEyJwp5vCtIgRRpQlxpfBTgZSxbGRJzYQU")

# DeepSeek API Key
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-8e6d7a7e7acf4202b013251e1ebc2d2a")

# DeepSeek Endpoint
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")

# Текст системного контекста и кодекса стиля — ослабленная версия с меньшим акцентом на повторяющиеся экспертные упоминания
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", """
Ты — девушка, литературный редактор книг в стиле магического реализма, исторический консультант по Османской Герцеговине 1820-х годов и эксперт по каббалистике, суфизму и дохристианским верованиям региона. Отвечай в стиле, соответствующем жанру, сохраняя литературную атмосферу и избегая повторных упоминаний своей роли.

ФОРМАТИРОВАНИЕ:
- Запрещены: эмодзи, любые виды разметки (markdown, HTML и т. п.), курсив, жирный, подчёркнутый текст.
- Списки допустимы только при объективной необходимости для чёткого структурирования фактов или алгоритмов.
- Обязателен сплошной текст, допускается деление только на абзацы.
""")

# Настройки DeepSeek
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.75"))
TOP_P = float(os.getenv("TOP_P", "0.85"))
FREQUENCY_PENALTY = float(os.getenv("FREQUENCY_PENALTY", "0.65"))
PRESENCE_PENALTY = float(os.getenv("PRESENCE_PENALTY", "0.6"))

# Функция динамического определения max_tokens в зависимости от длины запроса
def determine_max_tokens(user_message: str) -> int:
    length = len(user_message)
    if length < 50:
        return 1200
    elif length < 150:
        return 800
    else:
        return 400

# Пример использования в коде формирования запроса к DeepSeek API:
# max_tokens = determine_max_tokens(user_input)
# payload = {
#     "model": DEEPSEEK_MODEL,
#     "messages": [
#         {"role": "system", "content": SYSTEM_PROMPT},
#         {"role": "user", "content": user_input}
#     ],
#     "temperature": TEMPERATURE,
#     "max_tokens": max_tokens,
#     "top_p": TOP_P,
#     "frequency_penalty": FREQUENCY_PENALTY,
#     "presence_penalty": PRESENCE_PENALTY,
#     "stream": False
# }
