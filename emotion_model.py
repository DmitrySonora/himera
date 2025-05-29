from transformers import pipeline

# Для ускорения и предотвращения повторной загрузки — инициализируем один раз при старте
emotion_classifier = pipeline("text-classification", model="cointegrated/rubert-tiny2-cedr-emotion-detection", top_k=None)

def get_emotion(text):
    """
    Возвращает tuple: (emotion_label, confidence)
    """
    result = emotion_classifier(text)[0]  # Возвращает список словарей
    # Сортируем по score, берём топ-1
    best = max(result, key=lambda x: x['score'])
    return best['label'], float(best['score'])

