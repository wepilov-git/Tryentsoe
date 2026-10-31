import os
import time
import sqlite3
import pandas as pd
from entsoe import EntsoePandasClient
from datetime import datetime

# ==========================================
# 1. НАСТРОЙКИ И ОБЪЯВЛЕНИЕ ЛОГЕРА
# ==========================================
API_TOKEN = '71dbea05-02be-4d8d-9adf-95d5b7df8a17'
client = EntsoePandasClient(api_key=API_TOKEN)

COUNTRIES = ['DE', 'FR', 'NL', 'BE', 'CH', 'AT', 'PL', 'IT', 'ES', 'PT']

DB_DIR = r"/storage/emulated/0/Download"
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "entsoe_data.db")
LOG_PATH = os.path.join(DB_DIR, "entsoe_log.txt")

def log_message(message):
    """Функция логирования (должна быть первой)"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_message = f"[{timestamp}] {message}"
    print(full_message)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(full_message + "\n")
    except Exception as e:
        print(f"Не удалось записать лог в файл: {e}")

# ==========================================
# 2. ФУНКЦИИ РАБОТЫ С БАЗОЙ ДАННЫХ
# ==========================================
def init_db():
    """Создание БД и таблиц"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS load_and_forecast (
            country TEXT, timestamp TEXT, actual_load REAL, forecast_load REAL,
            PRIMARY KEY (country, timestamp)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS generation_forecast (
            country TEXT, timestamp TEXT, forecast_generation REAL,
            PRIMARY KEY (country, timestamp)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS generation_actual (
            country TEXT, timestamp TEXT, production_type TEXT, generation_value REAL,
            PRIMARY KEY (country, timestamp, production_type)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS day_ahead_prices (
            country TEXT, timestamp TEXT, price REAL,
            PRIMARY KEY (country, timestamp)
        )
    ''')
    conn.commit()
    conn.close()

def get_last_timestamp(cursor, country, default_days=2):
    """Поиск последней даты в базе"""
    tables = ['load_and_forecast', 'generation_forecast', 'generation_actual', 'day_ahead_prices']
    max_ts = None
    
    for table in tables:
        cursor.execute(f"SELECT MAX(timestamp) FROM {table} WHERE country = ?", (country,))
        row = cursor.fetchone()
        if row and row[0]:
            if max_ts is None or row[0] > max_ts:
                max_ts = row[0]
                
    if max_ts:
        return pd.Timestamp(max_ts, tz='Europe/Brussels') - pd.Timedelta(hours=2)
    else:
        return pd.Timestamp.now(tz='Europe/Brussels') - pd.Timedelta(days=default_days)

# ==========================================
# 3. ОСНОВНАЯ ФУНКЦИЯ СБОРА ДАННЫХ
# ==========================================
def fetch_and_save():
    init_db()
    
    end = pd.Timestamp.now(tz='Europe/Brussels')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for country in COUNTRIES:
        start = get_last_timestamp(cursor, country, default_days=2)
        
        if start >= end:
            start = end - pd.Timedelta(hours=1)
            
        log_message(f"Страна: [{country}] | Период: с {start.strftime('%m-%d %H:%M')} по {end.strftime('%m-%d %H:%M')}")
        
        # --- 1. load_and_forecast ---
        try:
            res_load = client.query_load_and_forecast(country, start=start, end=end)
            if isinstance(res_load, pd.DataFrame):
                updated = 0
                for timestamp, row in res_load.iterrows():
                    ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    act_val = float(row.iloc[0]) if pd.notnull(row.iloc[0]) else None
                    fc_val = float(row.iloc[1]) if len(row) > 1 and pd.notnull(row.iloc[1]) else None
                    
                    cursor.execute('''
                        INSERT INTO load_and_forecast (country, timestamp, actual_load, forecast_load)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(country, timestamp) DO UPDATE SET
                            actual_load = COALESCE(EXCLUDED.actual_load, load_and_forecast.actual_load),
                            forecast_load = COALESCE(EXCLUDED.forecast_load, load_and_forecast.forecast_load)
                    ''', (country, ts_str, act_val, fc_val))
                    updated += 1
                log_message(f" -> 'load_and_forecast': обработано {updated}")
        except Exception as e:
            log_message(f" [Пропущено] load: {e}")

        # --- 2. generation_forecast ---
        try:
            res_gen_fc = client.query_generation_forecast(country, start=start, end=end)
            if isinstance(res_gen_fc, pd.Series):
                res_gen_fc = res_gen_fc.to_frame()
            if isinstance(res_gen_fc, pd.DataFrame):
                updated = 0
                for timestamp, row in res_gen_fc.iterrows():
                    ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    val = float(row.iloc[0]) if pd.notnull(row.iloc[0]) else None
                    if val is not None:
                        cursor.execute('''
                            INSERT INTO generation_forecast (country, timestamp, forecast_generation)
                            VALUES (?, ?, ?)
                            ON CONFLICT(country, timestamp) DO UPDATE SET
                                forecast_generation = EXCLUDED.forecast_generation
                        ''', (country, ts_str, val))
                        updated += 1
                log_message(f" -> 'generation_forecast': обработано {updated}")
        except Exception as e:
            log_message(f" [Пропущено] gen_forecast: {e}")

        # --- 3. generation_actual ---
        try:
            res_gen_act = client.query_generation(country, start=start, end=end, psr_type=None)
            if isinstance(res_gen_act, pd.DataFrame):
                if isinstance(res_gen_act.columns, pd.MultiIndex):
                    res_gen_act.columns = [
                        f"{col[0]}_{col[1]}" if pd.notnull(col[1]) else col[0] 
                        for col in res_gen_act.columns
                    ]
                
                res_long = res_gen_act.stack().reset_index()
                res_long.columns = ['timestamp', 'production_type', 'generation_value']
                
                updated = 0
                for _, row in res_long.iterrows():
                    ts_str = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                    p_type = str(row['production_type'])
                    val = float(row['generation_value']) if pd.notnull(row['generation_value']) else None
                    
                    if val is not None:
                        cursor.execute('''
                            INSERT INTO generation_actual (country, timestamp, production_type, generation_value)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(country, timestamp, production_type) DO UPDATE SET
                                generation_value = EXCLUDED.generation_value
                        ''', (country, ts_str, p_type, val))
                        updated += 1
                log_message(f" -> 'generation_actual': обработано {updated}")
        except Exception as e:
            log_message(f" [Пропущено] gen_actual: {e}")

        # --- 4. day_ahead_prices ---
        try:
            res_prices = client.query_day_ahead_prices(country, start=start, end=end)
            if isinstance(res_prices, pd.Series):
                res_prices = res_prices.to_frame()
            if isinstance(res_prices, pd.DataFrame):
                updated = 0
                for timestamp, row in res_prices.iterrows():
                    ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    val = float(row.iloc[0]) if pd.notnull(row.iloc[0]) else None
                    if val is not None:
                        cursor.execute('''
                            INSERT INTO day_ahead_prices (country, timestamp, price)
                            VALUES (?, ?, ?)
                            ON CONFLICT(country, timestamp) DO UPDATE SET
                                price = EXCLUDED.price
                        ''', (country, ts_str, val))
                        updated += 1
                log_message(f" -> 'day_ahead_prices': обработано {updated}")
        except Exception as e:
            log_message(f" [Пропущено] prices: {e}")

        conn.commit()

    conn.close()

# ==========================================
# 4. БЕСКОНЕЧНЫЙ ТАЙМЕР ДЛЯ ФОНА
# ==========================================
if __name__ == "__main__":
    # 900 секунд = 15 минут
    INTERVAL_SECONDS = 900 
    
    log_message("=== ФОНОВЫЙ СЕРВИС ЗАПУЩЕН ===")
    
    while True:
        try:
            log_message("Старт синхронизации данных...")
            fetch_and_save()
            log_message("Синхронизация успешно завершена.")
        except Exception as main_error:
            log_message(f"КРИТИЧЕСКАЯ ОШИБКА СЕРВИСА: {main_error}")
            log_message("Ожидание 1 минуту перед повторной попыткой...")
            time.sleep(60)
            continue
            
        log_message(f"Сон на {INTERVAL_SECONDS / 60} минут до следующего запуска.\n")
        time.sleep(INTERVAL_SECONDS)

