#!/usr/bin/env python3
"""
Скрипт миграции базы данных для добавления поддержки авторизации
Добавляет недостающие колонки в существующую таблицу history
"""

import sqlite3
import os
from datetime import datetime

# Путь к БД (такой же как в проекте)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'history.db')

def migrate_database():
    """Миграция существующей БД"""
    print("🔄 Начинаем миграцию базы данных...")
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Файл БД не найден: {DB_PATH}")
        return False
    
    # Создаем резервную копию
    backup_path = DB_PATH + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    import shutil
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ Создана резервная копия: {backup_path}")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Проверяем существующую структуру таблицы history
        c.execute("PRAGMA table_info(history)")
        columns = [row[1] for row in c.fetchall()]
        print(f"📋 Существующие колонки в history: {columns}")
        
        # Добавляем недостающие колонки в history
        if 'emotion_primary' not in columns:
            c.execute('ALTER TABLE history ADD COLUMN emotion_primary TEXT')
            print("✅ Добавлена колонка emotion_primary")
        
        if 'emotion_confidence' not in columns:
            c.execute('ALTER TABLE history ADD COLUMN emotion_confidence REAL')
            print("✅ Добавлена колонка emotion_confidence")
        
        # Создаем новые таблицы (если их нет)
        
        # Таблица версий схемы БД
        c.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        ''')
        print("✅ Создана таблица schema_version")
        
        # Таблица пользователей
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                password_used TEXT,
                is_authorized BOOLEAN DEFAULT FALSE,
                authorized_until DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_auth DATETIME,
                warned_expiry BOOLEAN DEFAULT FALSE,
                failed_attempts INTEGER DEFAULT 0,
                blocked_until DATETIME
            )
        ''')
        print("✅ Создана таблица users")
        
        # Таблица лимитов сообщений
        c.execute('''
            CREATE TABLE IF NOT EXISTS message_limits (
                user_id INTEGER,
                date TEXT,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        print("✅ Создана таблица message_limits")
        
        # Таблица паролей
        c.execute('''
            CREATE TABLE IF NOT EXISTS passwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                password_text TEXT UNIQUE,
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                duration_days INTEGER,
                times_used INTEGER DEFAULT 0
            )
        ''')
        print("✅ Создана таблица passwords")
        
        # Таблица логов авторизации
        c.execute('''
            CREATE TABLE IF NOT EXISTS auth_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                password_masked TEXT,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        print("✅ Создана таблица auth_log")
        
        # Создаем индексы
        indexes = [
            ('idx_users_authorized_until', 'users', 'authorized_until'),
            ('idx_users_blocked_until', 'users', 'blocked_until'),
            ('idx_message_limits_date', 'message_limits', 'date'),
            ('idx_passwords_active', 'passwords', 'is_active'),
            ('idx_auth_log_timestamp', 'auth_log', 'timestamp')
        ]
        
        for index_name, table_name, column_name in indexes:
            try:
                c.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})')
                print(f"✅ Создан индекс {index_name}")
            except Exception as e:
                print(f"⚠️ Не удалось создать индекс {index_name}: {e}")
        
        # Устанавливаем версию схемы
        c.execute('INSERT OR REPLACE INTO schema_version (version) VALUES (?)', (1,))
        print("✅ Установлена версия схемы: 1")
        
        conn.commit()
        print("✅ Все изменения сохранены")
        
        # Проверяем результат
        c.execute("PRAGMA table_info(history)")
        new_columns = [row[1] for row in c.fetchall()]
        print(f"📋 Новые колонки в history: {new_columns}")
        
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in c.fetchall()]
        print(f"📋 Все таблицы в БД: {tables}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при миграции: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

def add_test_password():
    """Добавляем тестовый пароль для проверки"""
    try:
        # Используем функции из обновленного модуля
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        from history_db import add_password
        
        success = add_password("test123", "Тестовый пароль на 3 дня", 3)
        if success:
            print("✅ Добавлен тестовый пароль: test123 (3 дня)")
        else:
            print("⚠️ Тестовый пароль уже существует")
            
    except Exception as e:
        print(f"⚠️ Не удалось добавить тестовый пароль: {e}")

def main():
    print("🚀 МИГРАЦИЯ БАЗЫ ДАННЫХ ХИМЕРЫ")
    print("=" * 50)
    
    if migrate_database():
        print("\n🎉 МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print("=" * 50)
        
        # Добавляем тестовый пароль
        print("\n🔑 Добавляем тестовый пароль...")
        add_test_password()
        
        print("\n📖 Что дальше:")
        print("1. Запустите бота: python3 telegram_bot.py")
        print("2. Протестируйте авторизацию с паролем: test123")
        print("3. Проверьте /admin_stats для статистики")
        
    else:
        print("\n❌ МИГРАЦИЯ ПРЕРВАНА!")
        print("Проверьте логи выше для деталей ошибки")

if __name__ == "__main__":
    main()