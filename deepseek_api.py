import requests
import logging

from config import (
    DEEPSEEK_API_URL,
    DEEPSEEK_API_KEY,
    SYSTEM_PROMPT,
    DEEPSEEK_MODEL,
    TEMPERATURE,
    TOP_P,
    FREQUENCY_PENALTY,
    PRESENCE_PENALTY,
    # убираем MAX_TOKENS из импорта, т.к. он будет динамически вычисляться
)

logger = logging.getLogger("deepseek_api")

# Добавляем функцию для динамического выбора max_tokens
def determine_max_tokens(user_message: str) -> int:
    length = len(user_message)
    if length < 50:
        return 1200
    elif length < 150:
        return 800
    else:
        return 400

def ask_deepseek(user_message):
    """
    Отправляет запрос к DeepSeek API и возвращает сгенерированный ответ.
    В случае ошибки возвращает строку с объяснением проблемы.
    """
    max_tokens = determine_max_tokens(user_message)

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,  # теперь динамически
        "top_p": TOP_P,
        "frequency_penalty": FREQUENCY_PENALTY,
        "presence_penalty": PRESENCE_PENALTY,
        "stream": False
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        logger.info(f"Запрос к DeepSeek: {user_message[:100]}")
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        # Структура ответа: data['choices'][0]['message']['content']
        if "choices" in data and len(data["choices"]) > 0:
            answer = data["choices"][0]["message"]["content"]
            logger.info(f"Ответ DeepSeek: {answer[:100]}")
            return answer.strip()
        else:
            logger.error(f"Пустой ответ DeepSeek: {data}")
            return "Ошибка: Пустой ответ DeepSeek API"
    except requests.exceptions.Timeout:
        logger.error("Таймаут запроса к DeepSeek API")
        return "Ошибка: Превышено время ожидания ответа DeepSeek API"
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка соединения с DeepSeek API: {str(e)}")
        return "Ошибка: Не удалось связаться с DeepSeek API"
    except Exception as e:
        logger.error(f"Непредвиденная ошибка DeepSeek API: {str(e)}")
        return "Ошибка: Внутренняя ошибка при обращении к DeepSeek API"
