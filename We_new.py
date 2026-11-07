import os
import sqlite3
import requests
import pandas as pd
from datetime import datetime

# Налаштування папок та БД
DB_DIR = "/storage/emulated/0/1"
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "weather_data.db")

# Повний список 10 міст для аналізу кореляції з енергоринком
CITIES = {
    "Paris": {"lat": 48.8566, "lon": 2.3522},
    "Essen/Cologne": {"lat": 50.9375, "lon": 6.9603},
    "Amsterdam/Rotterdam": {"lat": 51.9244, "lon": 4.4777},
    "Stockholm": {"lat": 59.3293, "lon": 18.0686},
    "Copenhagen": {"lat": 55.6761, "lon": 12.5683},
    "Madrid": {"lat": 40.4168, "lon": -3.7038},
    "Milan": {"lat": 45.4642, "lon": 9.1900},
    "Warsaw/Katowice": {"lat": 50.2649, "lon": 19.0238},
    "Prague": {"lat": 50.0755, "lon": 14.4378},
    "Athens/Belgrade": {"lat": 44.7872, "lon": 20.4573}
}

def init_weather_db():
    """Створення таблиці для погоди"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather (
            timestamp TEXT,
            city_name TEXT,
            temperature REAL,
            pressure REAL,
            humidity REAL,
            wind_speed REAL,
            clouds REAL,
            PRIMARY KEY (timestamp, city_name)
        )
    """)
    conn.commit()
    conn.close()

def fetch_and_save_weather():
    init_weather_db()
    conn = sqlite3.connect(DB_PATH)
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("[" + current_time + "] Старт збору метеоданих для 10 міст...")
    
    headers = {
        "User-Agent": "TermuxEnergyBot/1.0 (energy.trader.ua@gmail.com)"
    }
    
    for city, coords in CITIES.items():
        lat = round(coords["lat"], 4)
        lon = round(coords["lon"], 4)
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={lat}&lon={lon}"
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(" [Пропущено] " + city + " Статус: " + str(response.status_code))
                continue
                
            data = response.json()
            timeseries = data["properties"]["timeseries"]
            
            records = []
            for item in timeseries[:72]:
                time_str = item["time"].replace("T", " ").replace("Z", "")
                try:
                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                    
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                instant = item["data"]["instant"]["details"]
                
                records.append((
                    formatted_time,
                    city,
                    instant.get("air_temperature"),
                    instant.get("air_pressure_at_sea_level"),
                    instant.get("relative_humidity"),
                    instant.get("wind_speed"),
                    instant.get("cloud_area_fraction")
                ))
            
            cursor = conn.cursor()
            cursor.executemany("INSERT OR IGNORE INTO weather VALUES (?,?,?,?,?,?,?)", records)
            conn.commit()
            print(" -> Місто " + city + ": успішно завантажено прогнози.")
            
        except Exception as e:
            print(" [Помилка] " + city + ": " + str(e))
            
    # Виведення підсумкової таблиці Pandas DataFrame в консоль
    print("\n[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "] Збір завершено. Свіжий зріз даних з бази:")
    try:
        # Вибираємо останні записи для кожного міста, щоб оцінити поточний стан
        query = """
            SELECT city_name, timestamp, temperature, pressure, wind_speed, clouds 
            FROM weather 
            WHERE timestamp >= datetime('now', '-1 hour')
            GROUP BY city_name
            ORDER BY city_name ASC
        """
        df_summary = pd.read_sql_query(query, conn)
        if not df_summary.empty:
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', 1000)
            print(df_summary.to_string(index=False))
        else:
            # Якщо за datetime('now') в базі порожньо через різницю часових поясів (CET vs UTC)
            print("Попередній перегляд (перші 15 рядків таблиці):")
            df_all = pd.read_sql_query("SELECT * FROM weather ORDER BY timestamp DESC LIMIT 15", conn)
            print(df_all.to_string(index=False))
    except Exception as db_err:
        print("Не вдалося вивести DataFrame: " + str(db_err))

    conn.close()

if __name__ == "__main__":
    fetch_and_save_weather()
