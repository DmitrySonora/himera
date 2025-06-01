import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

import os

# Определяем путь к БД относительно текущего файла
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'history.db')

def get_connection():
    """Простая функция для получения подключения к БД"""
    return sqlite3.connect(DB_PATH, timeout=30)

def init_db():
    """Инициализация базы данных с созданием всех необходимых таблиц"""
    conn = get_connection()
    c = conn.cursor()
    
    # Таблица истории сообщений (существующая)
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp DATETIME,
            emotion_primary TEXT,
            emotion_confidence REAL
        )
    ''')
    
    # Таблица версий схемы БД
    c.execute('''
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        )
    ''')
    
    # Таблица пользователей и их статусов авторизации
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
    
    # Таблица лимитов сообщений по дням
    c.execute('''
        CREATE TABLE IF NOT EXISTS message_limits (
            user_id INTEGER,
            date TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # Таблица временных паролей
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
    
    # Создание индексов для оптимизации
    c.execute('CREATE INDEX IF NOT EXISTS idx_users_authorized_until ON users(authorized_until)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_users_blocked_until ON users(blocked_until)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_message_limits_date ON message_limits(date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_passwords_active ON passwords(is_active)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_auth_log_timestamp ON auth_log(timestamp)')
    
    # Устанавливаем версию схемы
    c.execute('INSERT OR IGNORE INTO schema_version (version) VALUES (?)', (1,))
    
    conn.commit()
    conn.close()

def mask_password(password: str) -> str:
    """Маскирует пароль для логов: test123 -> te***23"""
    if not password:
        return ""
    if len(password) <= 4:
        return "*" * len(password)
    return password[:2] + "*" * (len(password) - 4) + password[-2:]

def log_auth_event(user_id: int, action: str, password: Optional[str] = None, details: Optional[str] = None):
    """Логирование событий авторизации"""
    conn = get_connection()
    c = conn.cursor()
    
    password_masked = mask_password(password) if password else None
    
    c.execute('''
        INSERT INTO auth_log (user_id, action, password_masked, details, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, action, password_masked, details, datetime.utcnow()))
    
    conn.commit()
    conn.close()

def ensure_user_exists(user_id: int):
    """Создает пользователя в БД, если его нет"""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    if not c.fetchone():
        c.execute('''
            INSERT INTO users (user_id, is_authorized, created_at)
            VALUES (?, FALSE, ?)
        ''', (user_id, datetime.utcnow()))
        conn.commit()
    
    conn.close()

def check_user_auth_status(user_id: int) -> Dict[str, Any]:
    """Проверка статуса авторизации пользователя"""
    ensure_user_exists(user_id)
    
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('''
        SELECT is_authorized, authorized_until, blocked_until, failed_attempts, warned_expiry
        FROM users WHERE user_id = ?
    ''', (user_id,))
    
    row = c.fetchone()
    conn.close()
    
    if not row:
        return {'authorized': False, 'blocked': False, 'expired': False}
    
    is_authorized, authorized_until, blocked_until, failed_attempts, warned_expiry = row
    now = datetime.utcnow()
    
    # Проверка блокировки
    if blocked_until and datetime.fromisoformat(blocked_until) > now:
        return {
            'authorized': False,
            'blocked': True,
            'blocked_until': blocked_until,
            'failed_attempts': failed_attempts
        }
    
    # Проверка истечения авторизации
    if is_authorized and authorized_until:
        auth_until = datetime.fromisoformat(authorized_until)
        if auth_until <= now:
            # Авторизация истекла - деактивируем
            conn = get_connection()
            c = conn.cursor()
            c.execute('''
                UPDATE users SET is_authorized = FALSE, warned_expiry = FALSE
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
            conn.close()
            
            log_auth_event(user_id, 'auto_expired', details=f'Авторизация истекла: {authorized_until}')
            
            return {'authorized': False, 'blocked': False, 'expired': True}
        
        return {
            'authorized': True,
            'blocked': False,
            'authorized_until': authorized_until,
            'warned_expiry': warned_expiry
        }
    
    return {'authorized': False, 'blocked': False, 'expired': False}

def check_daily_limit(user_id: int) -> Dict[str, Any]:
    """Проверка суточного лимита сообщений"""
    ensure_user_exists(user_id)
    
    today = datetime.utcnow().date().isoformat()
    
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('''
        SELECT count FROM message_limits 
        WHERE user_id = ? AND date = ?
    ''', (user_id, today))
    
    row = c.fetchone()
    current_count = row[0] if row else 0
    
    conn.close()
    
    from config import DAILY_MESSAGE_LIMIT
    
    return {
        'count': current_count,
        'limit': DAILY_MESSAGE_LIMIT,
        'remaining': max(0, DAILY_MESSAGE_LIMIT - current_count),
        'exceeded': current_count >= DAILY_MESSAGE_LIMIT
    }

def increment_message_count(user_id: int) -> int:
    """Увеличивает счетчик сообщений на 1, возвращает новое значение"""
    today = datetime.utcnow().date().isoformat()
    
    conn = get_connection()
    c = conn.cursor()
    
    # Используем INSERT OR REPLACE для atomic upsert
    c.execute('''
        INSERT OR REPLACE INTO message_limits (user_id, date, count)
        VALUES (?, ?, COALESCE((SELECT count FROM message_limits WHERE user_id = ? AND date = ?), 0) + 1)
    ''', (user_id, today, user_id, today))
    
    # Получаем новое значение
    c.execute('SELECT count FROM message_limits WHERE user_id = ? AND date = ?', (user_id, today))
    new_count = c.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    return new_count

def check_bruteforce_protection(user_id: int) -> Dict[str, Any]:
    """Проверка защиты от bruteforce атак"""
    auth_status = check_user_auth_status(user_id)
    
    if auth_status.get('blocked'):
        from datetime import datetime
        blocked_until = datetime.fromisoformat(auth_status['blocked_until'])
        remaining = blocked_until - datetime.utcnow()
        
        return {
            'blocked': True,
            'remaining_seconds': max(0, int(remaining.total_seconds())),
            'failed_attempts': auth_status['failed_attempts']
        }
    
    return {'blocked': False}

def process_password_attempt(user_id: int, password: str) -> Dict[str, Any]:
    """Обработка попытки ввода пароля - УПРОЩЕННАЯ ВЕРСИЯ"""
    from config import MAX_PASSWORD_ATTEMPTS, BRUTEFORCE_TIMEOUT
    
    # Убеждаемся что пользователь существует
    ensure_user_exists(user_id)
    
    # Проверяем пароль
    conn = get_connection()
    c = conn.cursor()
    
    # Проверяем существование и активность пароля
    c.execute('SELECT duration_days FROM passwords WHERE password_text = ? AND is_active = TRUE', (password,))
    password_row = c.fetchone()
    
    if password_row:
        # Пароль правильный
        duration_days = password_row[0]
        authorized_until = datetime.utcnow() + timedelta(days=duration_days)
        
        # Обновляем пользователя
        c.execute('''
            UPDATE users SET 
                is_authorized = TRUE,
                authorized_until = ?,
                password_used = ?,
                last_auth = ?,
                failed_attempts = 0,
                blocked_until = NULL,
                warned_expiry = FALSE
            WHERE user_id = ?
        ''', (authorized_until.isoformat(), password, datetime.utcnow().isoformat(), user_id))
        
        # Увеличиваем счетчик использований пароля
        c.execute('UPDATE passwords SET times_used = times_used + 1 WHERE password_text = ?', (password,))
        
        conn.commit()
        conn.close()
        
        log_auth_event(user_id, 'password_success', password, f'Авторизован на {duration_days} дней')
        
        return {
            'success': True,
            'duration_days': duration_days,
            'authorized_until': authorized_until.isoformat()
        }
    else:
        # Пароль неправильный
        # Получаем текущие попытки
        c.execute('SELECT failed_attempts FROM users WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        current_attempts = row[0] if row and row[0] else 0
        new_attempts = current_attempts + 1
        
        if new_attempts >= MAX_PASSWORD_ATTEMPTS:
            # Блокируем пользователя
            blocked_until = datetime.utcnow() + timedelta(seconds=BRUTEFORCE_TIMEOUT)
            c.execute('''
                UPDATE users SET 
                    failed_attempts = ?,
                    blocked_until = ?
                WHERE user_id = ?
            ''', (new_attempts, blocked_until.isoformat(), user_id))
            
            conn.commit()
            conn.close()
            
            log_auth_event(user_id, 'blocked', password, f'Заблокирован на {BRUTEFORCE_TIMEOUT} секунд')
            
            return {
                'success': False,
                'blocked': True,
                'remaining_attempts': 0,
                'blocked_seconds': BRUTEFORCE_TIMEOUT
            }
        else:
            # Увеличиваем счетчик попыток
            c.execute('UPDATE users SET failed_attempts = ? WHERE user_id = ?', (new_attempts, user_id))
            
            conn.commit()
            conn.close()
            
            log_auth_event(user_id, 'password_fail', password, f'Попытка {new_attempts}/{MAX_PASSWORD_ATTEMPTS}')
            
            return {
                'success': False,
                'blocked': False,
                'remaining_attempts': MAX_PASSWORD_ATTEMPTS - new_attempts
            }

# === АДМИНИСТРАТИВНЫЕ ФУНКЦИИ ===

def add_password(password: str, description: str, duration_days: int) -> bool:
    """Добавление временного пароля"""
    from config import AVAILABLE_DURATIONS
    
    if duration_days not in AVAILABLE_DURATIONS:
        raise ValueError(f"Недопустимая продолжительность. Доступны: {AVAILABLE_DURATIONS}")
    
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute('''
            INSERT INTO passwords (password_text, description, duration_days, created_at)
            VALUES (?, ?, ?, ?)
        ''', (password, description, duration_days, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False  # Пароль уже существует

def deactivate_password(password: str) -> bool:
    """Деактивация пароля"""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('UPDATE passwords SET is_active = FALSE WHERE password_text = ?', (password,))
    success = c.rowcount > 0
    
    conn.commit()
    conn.close()
    
    if success:
        log_auth_event(0, 'password_deactivated', password, 'Деактивирован администратором')
    
    return success

def list_passwords(show_full: bool = False) -> List[Dict[str, Any]]:
    """Список всех паролей с информацией"""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('''
        SELECT password_text, description, is_active, created_at, duration_days, times_used
        FROM passwords ORDER BY created_at DESC
    ''')
    
    passwords = []
    for row in c.fetchall():
        password_text, description, is_active, created_at, duration_days, times_used = row
        
        passwords.append({
            'password': password_text if show_full else mask_password(password_text),
            'description': description,
            'is_active': bool(is_active),
            'created_at': created_at,
            'duration_days': duration_days,
            'times_used': times_used
        })
    
    conn.close()
    return passwords

def get_password_stats() -> Dict[str, Any]:
    """Статистика по паролям"""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM passwords WHERE is_active = TRUE')
    active_count = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM passwords WHERE is_active = FALSE')
    inactive_count = c.fetchone()[0]
    
    c.execute('SELECT SUM(times_used) FROM passwords')
    total_uses = c.fetchone()[0] or 0
    
    c.execute('''
        SELECT duration_days, COUNT(*) 
        FROM passwords WHERE is_active = TRUE 
        GROUP BY duration_days ORDER BY duration_days
    ''')
    
    by_duration = {row[0]: row[1] for row in c.fetchall()}
    
    conn.close()
    
    return {
        'active_passwords': active_count,
        'inactive_passwords': inactive_count,
        'total_uses': total_uses,
        'by_duration': by_duration
    }

def get_user_stats(user_id: int) -> Dict[str, Any]:
    """Статистика пользователя"""
    conn = get_connection()
    c = conn.cursor()
    
    # Основная информация о пользователе
    c.execute('''
        SELECT created_at, last_auth, password_used, failed_attempts, warned_expiry
        FROM users WHERE user_id = ?
    ''', (user_id,))
    
    user_row = c.fetchone()
    
    if not user_row:
        return {'exists': False}
    
    created_at, last_auth, password_used, failed_attempts, warned_expiry = user_row
    
    # Счетчик сообщений за сегодня
    today = datetime.utcnow().date().isoformat()
    c.execute('SELECT count FROM message_limits WHERE user_id = ? AND date = ?', (user_id, today))
    today_messages = c.fetchone()
    today_count = today_messages[0] if today_messages else 0
    
    # Общее количество сообщений в истории
    c.execute('SELECT COUNT(*) FROM history WHERE user_id = ?', (user_id,))
    total_messages = c.fetchone()[0]
    
    conn.close()
    
    return {
        'exists': True,
        'created_at': created_at,
        'last_auth': last_auth,
        'password_used': mask_password(password_used) if password_used else None,
        'failed_attempts': failed_attempts,
        'warned_expiry': warned_expiry,
        'today_messages': today_count,
        'total_messages': total_messages
    }

def get_auth_log(user_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Просмотр логов авторизации"""
    conn = get_connection()
    c = conn.cursor()
    
    if user_id:
        c.execute('''
            SELECT user_id, action, password_masked, details, timestamp
            FROM auth_log WHERE user_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (user_id, limit))
    else:
        c.execute('''
            SELECT user_id, action, password_masked, details, timestamp
            FROM auth_log ORDER BY timestamp DESC LIMIT ?
        ''', (limit,))
    
    logs = []
    for row in c.fetchall():
        user_id, action, password_masked, details, timestamp = row
        logs.append({
            'user_id': user_id,
            'action': action,
            'password_masked': password_masked,
            'details': details,
            'timestamp': timestamp
        })
    
    conn.close()
    return logs

def get_blocked_users() -> List[Dict[str, Any]]:
    """Список заблокированных пользователей"""
    conn = get_connection()
    c = conn.cursor()
    
    now = datetime.utcnow().isoformat()
    c.execute('''
        SELECT user_id, blocked_until, failed_attempts
        FROM users 
        WHERE blocked_until IS NOT NULL AND blocked_until > ?
        ORDER BY blocked_until DESC
    ''', (now,))
    
    blocked = []
    for row in c.fetchall():
        user_id, blocked_until, failed_attempts = row
        remaining = datetime.fromisoformat(blocked_until) - datetime.utcnow()
        
        blocked.append({
            'user_id': user_id,
            'blocked_until': blocked_until,
            'failed_attempts': failed_attempts,
            'remaining_seconds': max(0, int(remaining.total_seconds()))
        })
    
    conn.close()
    return blocked

def unblock_user(user_id: int) -> bool:
    """Разблокировка пользователя вручную"""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('''
        UPDATE users SET blocked_until = NULL, failed_attempts = 0
        WHERE user_id = ? AND blocked_until IS NOT NULL
    ''', (user_id,))
    
    success = c.rowcount > 0
    
    conn.commit()
    conn.close()
    
    if success:
        log_auth_event(user_id, 'unblocked', details='Разблокирован администратором')
    
    return success

def cleanup_old_limits(days_keep: Optional[int] = None):
    """Очистка старых записей лимитов"""
    if days_keep is None:
        from config import CLEANUP_DAYS_KEEP
        days_keep = CLEANUP_DAYS_KEEP
    
    cutoff_date = (datetime.utcnow() - timedelta(days=days_keep)).date().isoformat()
    
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('DELETE FROM message_limits WHERE date < ?', (cutoff_date,))
    deleted_count = c.rowcount
    
    conn.commit()
    conn.close()
    
    return deleted_count

def cleanup_expired_users():
    """Очистка просроченных авторизаций"""
    now = datetime.utcnow().isoformat()
    
    conn = get_connection()
    c = conn.cursor()
    
    # Находим просроченных пользователей для логирования
    c.execute('''
        SELECT user_id, authorized_until FROM users 
        WHERE is_authorized = TRUE AND authorized_until <= ?
    ''', (now,))
    
    expired_users = c.fetchall()
    
    # Деактивируем их
    c.execute('''
        UPDATE users SET is_authorized = FALSE, warned_expiry = FALSE
        WHERE is_authorized = TRUE AND authorized_until <= ?
    ''', (now,))
    
    conn.commit()
    conn.close()
    
    # Логируем деактивацию
    for user_id, authorized_until in expired_users:
        log_auth_event(user_id, 'auto_expired', details=f'Авторизация истекла: {authorized_until}')
    
    return len(expired_users)

def add_message(user_id, role, content, emotion_primary=None, emotion_confidence=None):
    """Добавление сообщения в историю (расширенная версия)"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO history (user_id, role, content, timestamp, emotion_primary, emotion_confidence)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, role, content, datetime.utcnow(), emotion_primary, emotion_confidence))
    conn.commit()
    conn.close()

def get_history(user_id, limit=10):
    """Получение истории сообщений (существующая функция)"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT role, content, emotion_primary, emotion_confidence FROM history
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    
    messages = []
    for role, content, emotion_primary, emotion_confidence in reversed(rows):
        msg = {"role": role, "content": content}
        if emotion_primary:
            msg["emotion_primary"] = emotion_primary
        if emotion_confidence:
            msg["emotion_confidence"] = emotion_confidence
        messages.append(msg)
    
    return messages

def is_valid_password(password: str) -> bool:
    """Проверка, является ли строка действующим паролем"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM passwords WHERE password_text = ? AND is_active = TRUE', (password,))
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        print(f"Ошибка при проверке пароля: {e}")
        return False

def update_user_warning_flag(user_id: int) -> bool:
    """Обновление флага предупреждения об истечении"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('UPDATE users SET warned_expiry = TRUE WHERE user_id = ?', (user_id,))
        success = c.rowcount > 0
        conn.commit()
        conn.close()
        return success
    except Exception as e:
        print(f"Ошибка при обновлении флага предупреждения: {e}")
        return False

def logout_user(user_id: int) -> bool:
    """Выход пользователя из системы"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('UPDATE users SET is_authorized = FALSE WHERE user_id = ?', (user_id,))
        success = c.rowcount > 0
        conn.commit()
        conn.close()
        
        if success:
            log_auth_event(user_id, 'manual_logout', details='Пользователь вышел сам')
        
        return success
    except Exception as e:
        print(f"Ошибка при logout: {e}")
        return False

def get_users_stats() -> Dict[str, int]:
    """Получение статистики пользователей"""
    try:
        conn = get_connection()
        c = conn.cursor()
        
        c.execute('SELECT COUNT(*) FROM users WHERE is_authorized = TRUE')
        active_users = c.fetchone()[0]
        
        c.execute('SELECT COUNT(DISTINCT user_id) FROM users')
        total_users = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM users WHERE blocked_until > datetime("now")')
        blocked_users = c.fetchone()[0]
        
        conn.close()
        
        return {
            'active_users': active_users,
            'total_users': total_users,
            'blocked_users': blocked_users
        }
    except Exception as e:
        print(f"Ошибка при получении статистики пользователей: {e}")
        return {
            'active_users': 0,
            'total_users': 0,
            'blocked_users': 0
        }

# Инициализация БД при импорте модуля
init_db()