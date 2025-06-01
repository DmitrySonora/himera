#!/usr/bin/env python3
"""
Скрипт для управления паролями бота Химера
Использование:
    python3 manage_passwords.py --add "пароль" --days 30 --desc "Описание"
    python3 manage_passwords.py --list
    python3 manage_passwords.py --list --full
    python3 manage_passwords.py --deactivate "пароль"
    python3 manage_passwords.py --stats
    python3 manage_passwords.py --cleanup
    python3 manage_passwords.py --logs [--user USER_ID]
    python3 manage_passwords.py --blocked
    python3 manage_passwords.py --unblock USER_ID
"""

import argparse
import sys
import os
from datetime import datetime

# Добавляем путь к модулям проекта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from history_db import *
    from config import AVAILABLE_DURATIONS
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Убедитесь, что скрипт запускается из директории проекта")
    sys.exit(1)

def add_password_cmd(password: str, days: int, description: str):
    """Добавление нового пароля"""
    try:
        if days not in AVAILABLE_DURATIONS:
            print(f"❌ Недопустимая продолжительность: {days}")
            print(f"Доступные варианты: {AVAILABLE_DURATIONS}")
            return False
        
        success = add_password(password, description, days)
        if success:
            print(f"✅ Пароль '{password}' успешно добавлен на {days} дней")
            print(f"   Описание: {description}")
            return True
        else:
            print(f"❌ Пароль '{password}' уже существует")
            return False
    except Exception as e:
        print(f"❌ Ошибка при добавлении пароля: {e}")
        return False

def list_passwords_cmd(show_full: bool = False):
    """Просмотр списка паролей"""
    try:
        passwords = list_passwords(show_full=show_full)
        
        if not passwords:
            print("📝 Паролей не найдено")
            return
        
        print(f"📋 СПИСОК ПАРОЛЕЙ ({len(passwords)} шт.):")
        print("-" * 80)
        
        for i, p in enumerate(passwords, 1):
            status = "🟢 Активен" if p['is_active'] else "🔴 Деактивирован"
            created = datetime.fromisoformat(p['created_at']).strftime("%Y-%m-%d %H:%M")
            
            print(f"{i:2}. {p['password']}")
            print(f"    Описание: {p['description']}")
            print(f"    Длительность: {p['duration_days']} дней")
            print(f"    Статус: {status}")
            print(f"    Создан: {created}")
            print(f"    Использований: {p['times_used']}")
            print()
            
    except Exception as e:
        print(f"❌ Ошибка при получении списка: {e}")

def deactivate_password_cmd(password: str):
    """Деактивация пароля"""
    try:
        success = deactivate_password(password)
        if success:
            print(f"✅ Пароль '{password}' успешно деактивирован")
            return True
        else:
            print(f"❌ Пароль '{password}' не найден")
            return False
    except Exception as e:
        print(f"❌ Ошибка при деактивации: {e}")
        return False

def show_stats_cmd():
    """Показ статистики"""
    try:
        stats = get_password_stats()
        
        print("📊 СТАТИСТИКА ПАРОЛЕЙ:")
        print("-" * 40)
        print(f"Активных паролей: {stats['active_passwords']}")
        print(f"Деактивированных: {stats['inactive_passwords']}")
        print(f"Всего использований: {stats['total_uses']}")
        
        if stats['by_duration']:
            print("\nПо длительности:")
            for days, count in stats['by_duration'].items():
                print(f"  {days} дней: {count} паролей")
        
        # Дополнительная статистика по пользователям
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('SELECT COUNT(*) FROM users WHERE is_authorized = TRUE')
        active_users = c.fetchone()[0]
        
        c.execute('SELECT COUNT(DISTINCT user_id) FROM users')
        total_users = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM users WHERE blocked_until > datetime("now")')
        blocked_users = c.fetchone()[0]
        
        conn.close()
        
        print(f"\n👥 ПОЛЬЗОВАТЕЛИ:")
        print("-" * 40)
        print(f"Всего зарегистрировано: {total_users}")
        print(f"Сейчас авторизовано: {active_users}")
        print(f"Заблокировано: {blocked_users}")
        
    except Exception as e:
        print(f"❌ Ошибка при получении статистики: {e}")

def cleanup_cmd():
    """Очистка старых данных"""
    try:
        print("🧹 ОЧИСТКА СТАРЫХ ДАННЫХ:")
        print("-" * 40)
        
        deleted_limits = cleanup_old_limits()
        print(f"Удалено старых лимитов: {deleted_limits}")
        
        expired_users = cleanup_expired_users()
        print(f"Деактивировано просроченных: {expired_users}")
        
        print("✅ Очистка завершена")
        
    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")

def show_logs_cmd(user_id: int = None, limit: int = 20):
    """Показ логов авторизации"""
    try:
        logs = get_auth_log(user_id=user_id, limit=limit)
        
        if not logs:
            print("📝 Логов не найдено")
            return
        
        header = f"📜 ЛОГИ АВТОРИЗАЦИИ"
        if user_id:
            header += f" (пользователь {user_id})"
        header += f" - последние {len(logs)} записей:"
        
        print(header)
        print("-" * 80)
        
        for log in logs:
            timestamp = datetime.fromisoformat(log['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
            action_emoji = {
                'password_success': '✅',
                'password_fail': '❌',
                'auto_expired': '⏰',
                'blocked': '🚫',
                'unblocked': '🔓',
                'password_deactivated': '🗑️'
            }.get(log['action'], '📝')
            
            print(f"{action_emoji} {timestamp} | User {log['user_id']} | {log['action']}")
            if log['password_masked']:
                print(f"    Пароль: {log['password_masked']}")
            if log['details']:
                print(f"    Детали: {log['details']}")
            print()
            
    except Exception as e:
        print(f"❌ Ошибка при получении логов: {e}")

def show_blocked_cmd():
    """Показ заблокированных пользователей"""
    try:
        blocked = get_blocked_users()
        
        if not blocked:
            print("✅ Заблокированных пользователей нет")
            return
        
        print(f"🚫 ЗАБЛОКИРОВАННЫЕ ПОЛЬЗОВАТЕЛИ ({len(blocked)} шт.):")
        print("-" * 60)
        
        for user in blocked:
            blocked_until = datetime.fromisoformat(user['blocked_until']).strftime("%Y-%m-%d %H:%M:%S")
            remaining_min = user['remaining_seconds'] // 60
            
            print(f"User {user['user_id']}:")
            print(f"  Заблокирован до: {blocked_until}")
            print(f"  Осталось минут: {remaining_min}")
            print(f"  Неудачных попыток: {user['failed_attempts']}")
            print()
            
    except Exception as e:
        print(f"❌ Ошибка при получении списка: {e}")

def unblock_user_cmd(user_id: int):
    """Разблокировка пользователя"""
    try:
        success = unblock_user(user_id)
        if success:
            print(f"✅ Пользователь {user_id} разблокирован")
            return True
        else:
            print(f"❌ Пользователь {user_id} не найден или не заблокирован")
            return False
    except Exception as e:
        print(f"❌ Ошибка при разблокировке: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Управление паролями бота Химера",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  Добавить пароль:
    python3 manage_passwords.py --add "test123" --days 3 --desc "Тестовый пароль"
    python3 manage_passwords.py --add "месячный" --days 30 --desc "Доступ на месяц"

  Просмотр паролей:
    python3 manage_passwords.py --list
    python3 manage_passwords.py --list --full    (показать пароли полностью)

  Деактивация:
    python3 manage_passwords.py --deactivate "test123"

  Статистика и логи:
    python3 manage_passwords.py --stats
    python3 manage_passwords.py --logs
    python3 manage_passwords.py --logs --user 123456789

  Управление блокировками:
    python3 manage_passwords.py --blocked
    python3 manage_passwords.py --unblock 123456789

  Очистка:
    python3 manage_passwords.py --cleanup
        """)
    
    # Основные команды
    parser.add_argument('--add', type=str, help='Добавить новый пароль')
    parser.add_argument('--days', type=int, help='Продолжительность в днях (3, 30, 180, 365)')
    parser.add_argument('--desc', type=str, help='Описание пароля')
    
    parser.add_argument('--list', action='store_true', help='Показать список паролей')
    parser.add_argument('--full', action='store_true', help='Показать пароли полностью (только с --list)')
    
    parser.add_argument('--deactivate', type=str, help='Деактивировать пароль')
    parser.add_argument('--stats', action='store_true', help='Показать статистику')
    parser.add_argument('--cleanup', action='store_true', help='Очистить старые данные')
    
    parser.add_argument('--logs', action='store_true', help='Показать логи авторизации')
    parser.add_argument('--user', type=int, help='ID пользователя для фильтрации логов')
    
    parser.add_argument('--blocked', action='store_true', help='Показать заблокированных пользователей')
    parser.add_argument('--unblock', type=int, help='Разблокировать пользователя по ID')
    
    args = parser.parse_args()
    
    # Проверка аргументов
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    
    # Выполнение команд
    try:
        if args.add:
            if not args.days or not args.desc:
                print("❌ Для добавления пароля нужны параметры --days и --desc")
                return 1
            return 0 if add_password_cmd(args.add, args.days, args.desc) else 1
        
        elif args.list:
            list_passwords_cmd(show_full=args.full)
            return 0
        
        elif args.deactivate:
            return 0 if deactivate_password_cmd(args.deactivate) else 1
        
        elif args.stats:
            show_stats_cmd()
            return 0
        
        elif args.cleanup:
            cleanup_cmd()
            return 0
        
        elif args.logs:
            show_logs_cmd(user_id=args.user)
            return 0
        
        elif args.blocked:
            show_blocked_cmd()
            return 0
        
        elif args.unblock:
            return 0 if unblock_user_cmd(args.unblock) else 1
        
        else:
            print("❌ Укажите одну из команд. Используйте --help для справки")
            return 1
    
    except KeyboardInterrupt:
        print("\n⏹️ Операция прервана пользователем")
        return 1
    except Exception as e:
        print(f"❌ Непредвиденная ошибка: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())