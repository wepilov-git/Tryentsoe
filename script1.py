import os
import time
import sqlite3
import pandas as pd
from datetime import datetime
from entsoe import EntsoePandasClient
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 1. НАСТРОЙКИ И ОБЪЯВЛЕНИЕ ЛОГЕРА
# ==========================================
API_TOKEN = '71dbea05-02be-4d8d-9adf-95d5b7df8a17'
client = EntsoePandasClient(api_key=API_TOKEN)
COUNTRIES = ['DE', 'FR', 'NL', 'BE', 'CH', 'AT', 'PL', 'IT', 'ES', 'PT']

DB_DIR = r"/storage/emulated/0/1"
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "entsoe_data2.db")
LOG_PATH = os.path.join(DB_DIR, "entsoe_log.txt")
OUTPUT_HTML = os.path.join(DB_DIR, "entsoe_dashboard.html")

def log_message(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_message = f"[{timestamp}] {message}"
    print(full_message)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(full_message + "\n")
    except Exception as e:
        print(f"Не удалось записать лог: {e}")

# ==========================================
# 2. ФУНКЦИИ РАБОТЫ С БАЗОЙ ДАННЫХ
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS load_and_forecast (
        country TEXT, timestamp TEXT, actual_load REAL, forecast_load REAL, PRIMARY KEY (country, timestamp))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS generation_forecast (
        country TEXT, timestamp TEXT, forecast_generation REAL, PRIMARY KEY (country, timestamp))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS generation_actual (
        country TEXT, timestamp TEXT, production_type TEXT, generation_value REAL, PRIMARY KEY (country, timestamp, production_type))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS day_ahead_prices (
        country TEXT, timestamp TEXT, price REAL, PRIMARY KEY (country, timestamp))''')
    conn.commit()
    conn.close()

def get_last_timestamp(cursor, country, default_days=2):
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
    return pd.Timestamp.now(tz='Europe/Brussels') - pd.Timedelta(days=default_days)

# ==========================================
# 3. АВТОМАТИЧЕСКАЯ ВИЗУАЛИЗАЦИЯ
# ==========================================
def generate_browser_charts():
    log_message("Старт автоматической регенерации графиков и таблицы...")
    try:
        conn = sqlite3.connect(DB_PATH)
        df_load = pd.read_sql_query("SELECT * FROM load_and_forecast WHERE actual_load IS NOT NULL", conn)
        df_gen_act = pd.read_sql_query("SELECT * FROM generation_actual WHERE generation_value IS NOT NULL", conn)
        df_prices = pd.read_sql_query("SELECT * FROM day_ahead_prices WHERE price IS NOT NULL", conn)
        
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(timestamp) FROM generation_actual WHERE country = 'FR'")
        max_fr_ts_row = cursor.fetchone()
        fr_table_html = "<p style='text-align:center; color:#777;'>Нет данных по Франции за последние 15 минут.</p>"
        
        if max_fr_ts_row and max_fr_ts_row[0]:
            last_fr_ts = max_fr_ts_row[0]
            df_table_gen = pd.read_sql_query("SELECT production_type, generation_value FROM generation_actual WHERE country = 'FR' AND timestamp = ?", conn, params=(last_fr_ts,))
            df_table_load = pd.read_sql_query("SELECT actual_load, forecast_load FROM load_and_forecast WHERE country = 'FR' AND timestamp = ?", conn, params=(last_fr_ts,))
            df_table_price = pd.read_sql_query("SELECT price FROM day_ahead_prices WHERE country = 'FR' AND timestamp = ?", conn, params=(last_fr_ts,))
            
            load_val = f"{df_table_load['actual_load'].iloc[0]:,.2f} MW" if not df_table_load.empty and pd.notnull(df_table_load['actual_load'].iloc[0]) else "N/A"
            load_fc = f"{df_table_load['forecast_load'].iloc[0]:,.2f} MW" if not df_table_load.empty and len(df_table_load.columns) > 1 and pd.notnull(df_table_load['forecast_load'].iloc[0]) else "N/A"
            price_val = f"{df_table_price['price'].iloc[0]:,.2f} EUR/MWh" if not df_table_price.empty else "N/A"
            
            rows_html = f"""
            <tr style='background-color: #f1f5f9; font-weight: bold;'><td>Потребление (Actual Load)</td><td>{load_val}</td></tr>
            <tr style='background-color: #f1f5f9; font-weight: bold; border-bottom: 2px solid #cbd5e1;'><td>Прогноз нагрузки (Forecast Load)</td><td>{load_fc}</td></tr>
            <tr style='background-color: #fef08a; font-weight: bold; border-bottom: 2px solid #cbd5e1;'><td>Цена Day-Ahead</td><td>{price_val}</td></tr>"""
            
            for _, row in df_table_gen.iterrows():
                clean_name = row['production_type'].replace('_Actual', '').replace('_Generation', '')
                rows_html += f"<tr><td>Генерация: {clean_name}</td><td>{row['generation_value']:,.2f} MW</td></tr>"
                
            fr_table_html = f"""
            <div style="margin: 30px auto; max-width: 800px; font-family: sans-serif;">
                <h2 style="text-align: center; color: #1e293b;">Франция (FR) — Последние 15 минут</h2>
                <p style="text-align: center; color: #64748b; font-size: 14px;">Время среза данных: <b>{last_fr_ts} (CET)</b></p>
                <table style="width: 100%; border-collapse: collapse; background: white; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden;">
                    <thead><tr style="background-color: #1e3a8a; color: white;"><th style="padding: 12px;">Показатель</th><th style="padding: 12px;">Значение</th></tr></thead>
                    <tbody style="color: #334155; font-size: 14px;">{rows_html}</tbody>
                </table>
            </div>"""
        conn.close()
        
        if df_load.empty or df_gen_act.empty:
            log_message("Недостаточно данных для Plotly.")
            with open(OUTPUT_HTML, "w", encoding="utf-8") as f: f.write(fr_table_html)
            return
            
        df_load['timestamp'] = pd.to_datetime(df_load['timestamp'])
        df_gen_act['timestamp'] = pd.to_datetime(df_gen_act['timestamp'])
        if not df_prices.empty: df_prices['timestamp'] = pd.to_datetime(df_prices['timestamp'])
            
        max_ts = df_gen_act['timestamp'].max()
        df_gen_24h = df_gen_act[df_gen_act['timestamp'] >= (max_ts - pd.Timedelta(hours=24))]
        
        fig = make_subplots(rows=3, cols=1, subplot_titles=(
            "Сумарне споживання електроенергії (MWh)", "Динаміка генерації за 24 години (MW)", "Ціни Day-Ahead (EUR/MWh)"
        ), vertical_spacing=0.07, specs=[[{"type": "domain"}], [{"type": "xy"}], [{"type": "xy"}]])
        
        df_pie = df_load.groupby('country')['actual_load'].sum().reset_index()
        fig.add_trace(go.Pie(labels=df_pie['country'], values=df_pie['actual_load'], name="Потребление"), row=1, col=1)
        
        df_gen_grouped = df_gen_24h.groupby(['timestamp', 'production_type'])['generation_value'].sum().unstack(fill_value=0)
        for col in df_gen_grouped.columns:
            fig.add_trace(go.Scatter(x=df_gen_grouped.index, y=df_gen_grouped[col], mode='lines', name=col.replace('_Actual','').replace('_Generation','')), row=2, col=1)
            
        if not df_prices.empty:
            df_prices_grouped = df_prices.groupby(['timestamp', 'country'])['price'].first().unstack()
            for country_col in df_prices_grouped.columns:
                fig.add_trace(go.Scatter(x=df_prices_grouped.index, y=df_prices_grouped[country_col], mode='lines', name=f"Цена {country_col}"), row=3, col=1)
        
        fig.update_layout(height=1400, title_text=f"Дашборд ENTSO-E ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})", showlegend=True)
        plotly_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
        
        full_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>ENTSO-E</title>
        <style>body {{ background-color:#f8fafc; font-family:sans-serif; }} .container {{ max-width:1200px; margin:0 auto; padding:20px; }}</style>
        </head><body><div class="container">{fr_table_html}<div style="background:white; padding:15px; border-radius:8px; box-shadow:0 4px 6px rgba(0,0,0,0.1); margin-top:20px;">{plotly_html}</div></div></body></html>"""
        
        with open(OUTPUT_HTML, "w", encoding="utf-8") as f: f.write(full_html)
        log_message(f"Дашборд сохранен в: {OUTPUT_HTML}")
    except Exception as chart_error:
        log_message(f"Ошибка визуализации: {chart_error}")
# ==========================================
# 4. ОСНОВНАЯ ФУНКЦИЯ СБОРА ДАННЫХ
# ==========================================
def fetch_and_save():
    init_db()
    end = pd.Timestamp.now(tz='Europe/Brussels')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for country in COUNTRIES:
        start = get_last_timestamp(cursor, country, default_days=2)
        if start >= end: start = end - pd.Timedelta(hours=1)
        log_message(f"Страна: [{country}] | с {start.strftime('%m-%d %H:%M')} по {end.strftime('%m-%d %H:%M')}")
        
        try:
            res_load = client.query_load_and_forecast(country, start=start, end=end)
            if isinstance(res_load, pd.DataFrame):
                updated = 0
                for timestamp, row in res_load.iterrows():
                    ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    act_val = float(row.iloc[0]) if pd.notnull(row.iloc[0]) else None
                    fc_val = float(row.iloc[1]) if len(row) > 1 and pd.notnull(row.iloc[1]) else None
                    cursor.execute('''INSERT INTO load_and_forecast (country, timestamp, actual_load, forecast_load) VALUES (?, ?, ?, ?)
                        ON CONFLICT(country, timestamp) DO UPDATE SET actual_load=COALESCE(EXCLUDED.actual_load, load_and_forecast.actual_load), forecast_load=COALESCE(EXCLUDED.forecast_load, load_and_forecast.forecast_load)''', (country, ts_str, act_val, fc_val))
                    updated += 1
                log_message(f"  -> 'load_and_forecast': {updated}")
        except Exception as e: log_message(f"  [Пропущено] load: {e}")
            
        try:
            res_gen_fc = client.query_generation_forecast(country, start=start, end=end)
            if isinstance(res_gen_fc, pd.Series): res_gen_fc = res_gen_fc.to_frame()
            if isinstance(res_gen_fc, pd.DataFrame):
                updated = 0
                for timestamp, row in res_gen_fc.iterrows():
                    ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    val = float(row.iloc[0]) if pd.notnull(row.iloc[0]) else None
                    if val is not None:
                        cursor.execute('''INSERT INTO generation_forecast (country, timestamp, forecast_generation) VALUES (?, ?, ?)
                            ON CONFLICT(country, timestamp) DO UPDATE SET forecast_generation = EXCLUDED.forecast_generation''', (country, ts_str, val))
                        updated += 1
                log_message(f"  -> 'generation_forecast': {updated}")
        except Exception as e: log_message(f"  [Пропущено] gen_forecast: {e}")
            
        try:
            res_gen_act = client.query_generation(country, start=start, end=end, psr_type=None)
            if isinstance(res_gen_act, pd.DataFrame):
                if isinstance(res_gen_act.columns, pd.MultiIndex):
                    res_gen_act.columns = [f"{col[0]}_{col[1]}" if pd.notnull(col[1]) else col[0] for col in res_gen_act.columns]
                res_long = res_gen_act.stack().reset_index()
                res_long.columns = ['timestamp', 'production_type', 'generation_value']
                updated = 0
                for _, row in res_long.iterrows():
                    ts_str = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                    p_type = str(row['production_type'])
                    val = float(row['generation_value']) if pd.notnull(row['generation_value']) else None
                    if val is not None:
                        cursor.execute('''INSERT INTO generation_actual (country, timestamp, production_type, generation_value) VALUES (?, ?, ?, ?)
                            ON CONFLICT(country, timestamp, production_type) DO UPDATE SET generation_value = EXCLUDED.generation_value''', (country, ts_str, p_type, val))
                        updated += 1
                log_message(f"  -> 'generation_actual': {updated}")
        except Exception as e: log_message(f"  [Пропущено] gen_actual: {e}")
            
        try:
            res_prices = client.query_day_ahead_prices(country, start=start, end=end)
            if isinstance(res_prices, pd.Series): res_prices = res_prices.to_frame()
            if isinstance(res_prices, pd.DataFrame):
                updated = 0
                for timestamp, row in res_prices.iterrows():
                    ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    val = float(row.iloc[0]) if pd.notnull(row.iloc[0]) else None
                    if val is not None:
                        cursor.execute('''INSERT INTO day_ahead_prices (country, timestamp, price) VALUES (?, ?, ?)
                            ON CONFLICT(country, timestamp) DO UPDATE SET price = EXCLUDED.price''', (country, ts_str, val))
                        updated += 1
                log_message(f"  -> 'day_ahead_prices': {updated}")
        except Exception as e: log_message(f"  [Пропущено] prices: {e}")
            
    conn.commit()
    conn.close()

# ==========================================
# 5. БЕСКОНЕЧНЫЙ ТАЙМЕР ДЛЯ ФОНА
# ==========================================
if __name__ == "__main__":
    INTERVAL_SECONDS = 900
    log_message("=== ФОНОВЫЙ СЕРВИС С АВТО-ВИЗУАЛИЗАЦИЕЙ ЗАПУЩЕН ===")
    while True:
        try:
            log_message("Старт синхронизации данных...")
            fetch_and_save()
            log_message("Синхронизация успешно завершена.")
            generate_browser_charts()
        except Exception as main_error:
            log_message(f"КРИТИЧЕСКАЯ ОШИБКА СЕРВИСА: {main_error}")
            log_message("Ожидание 1 минуту перед повторной попыткой...")
            time.sleep(60)
            continue
        log_message(f"Сон на {INTERVAL_SECONDS / 60} минут до следующего запуска.\n")
        time.sleep(INTERVAL_SECONDS)
