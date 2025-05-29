import httpx
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
)

logger = logging.getLogger("deepseek_api")

def determine_max_tokens(user_message: str) -> int:
    length = len(user_message)
    if length < 50:
        return 1200
    elif length < 150:
        return 800
    else:
        return 400

async def ask_deepseek(user_message: str) -> str:
    max_tokens = determine_max_tokens(user_message)

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
        "top_p": TOP_P,
        "frequency_penalty": FREQUENCY_PENALTY,
        "presence_penalty": PRESENCE_PENALTY,
        "stream": False
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            logger.info(f"Запрос к DeepSeek: {user_message[:100]}")
            response = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                answer = data["choices"][0]["message"]["content"]
                logger.info(f"Ответ DeepSeek: {answer[:100]}")
                return answer.strip()
            else:
                logger.error(f"Пустой ответ DeepSeek: {data}")
                return "Ошибка: Пустой ответ DeepSeek API"
        except httpx.RequestError as e:
            logger.error(f"Ошибка соединения с DeepSeek API: {str(e)}")
            return "Ошибка: Не удалось связаться с DeepSeek API"
        except Exception as e:
            logger.error(f"Непредвиденная ошибка DeepSeek API: {str(e)}")
            return "Ошибка: Внутренняя ошибка при обращении к DeepSeek API"
