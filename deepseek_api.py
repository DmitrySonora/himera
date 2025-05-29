import requests
import logging

from config import (
    DEEPSEEK_API_URL,
    DEEPSEEK_API_KEY,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_EXPERT,
    SYSTEM_PROMPT_LIGHT,
    SYSTEM_PROMPT_FLIRT,
    DEEPSEEK_MODEL,
    TEMPERATURE,
    MAX_TOKENS,
    TOP_P,
    FREQUENCY_PENALTY,
    PRESENCE_PENALTY
)

logger = logging.getLogger("deepseek_api")

def ask_deepseek(user_message, mode="auto"):
    """
    Отправляет запрос к DeepSeek API и возвращает сгенерированный ответ.
    Поддерживает разные режимы ответа: expert, light, flirt, auto.
    """
    if mode == "expert":
        prompt = SYSTEM_PROMPT_EXPERT
    elif mode == "light":
        prompt = SYSTEM_PROMPT_LIGHT
    elif mode == "flirt":
        prompt = SYSTEM_PROMPT_FLIRT
    else:
        prompt = SYSTEM_PROMPT

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": prompt
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
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
        logger.info(f"Запрос к DeepSeek: {user_message[:100]} (режим: {mode})")
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
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
