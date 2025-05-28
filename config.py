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

# Текст системного контекста и кодекса стиля
# Здесь должна быть ваша строка с контекстом (добавьте свою версию)
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", """
Литературный редактор книг в стиле магического реализма. Исторический консультант по Османской Герцеговине 1820-х годов. Эксперт по каббалистике, суфизму и дохристианским верованиям этого региона. И просто хороший и весёлый собеседник.
""")

# Настройки DeepSeek
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.75"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1200"))
TOP_P = float(os.getenv("TOP_P", "0.85"))
FREQUENCY_PENALTY = float(os.getenv("FREQUENCY_PENALTY", "0.65"))
PRESENCE_PENALTY = float(os.getenv("PRESENCE_PENALTY", "0.6"))
