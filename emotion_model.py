# emotion_model.py

from transformers import pipeline

# Инициализация пайплайна один раз при импорте модуля
emotion_classifier = pipeline(
    "text-classification",
    model="cointegrated/rubert-tiny2-cedr-emotion-detection",
    top_k=None
)

def get_emotion(text):
    """
    Анализирует эмоцию в русском тексте.
    Возвращает tuple: (основная эмоция, confidence)
    """
    if not text.strip():
        return "neutral", 1.0  # На пустой/пробельный текст — по умолчанию
    result = emotion_classifier(text)[0]
    best = max(result, key=lambda x: x['score'])
    return best['label'], float(best['score'])

# Пример запуска (можно удалить после теста):
if __name__ == "__main__":
    test_text = "Я сегодня очень рад тебя видеть!"
    emotion, conf = get_emotion(test_text)
    print(f"Эмоция: {emotion}, уверенность: {conf:.2f}")
