from transformers import pipeline

# Для ускорения и предотвращения повторной загрузки — инициализируем один раз при старте
emotion_classifier = pipeline("text-classification", model="cointegrated/rubert-tiny2-cedr-emotion-detection", top_k=None)

