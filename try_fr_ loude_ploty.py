# %% [markdown]
# ### БЛОК 0: Инициализация окружения (Запускать обязательно один раз)

import os
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from entsoe import EntsoePandasClient

# Путь к вашей базе данных
TARGET_DIR = "/Users/alexandrandreevich/1.VS_python/ALL_DB"
DB_NAME = os.path.join(TARGET_DIR, "entsoe_data.db")
COUNTRY_CODE = 'FR'

# Проверка и создание папки
if not os.path.exists(TARGET_DIR):
    os.makedirs(TARGET_DIR)
    print(f"Создана директория для баз данных: {TARGET_DIR}")
else:
    print(f"Директория готова. БД будет сохранена по пути: {DB_NAME}")


# %% [markdown]
# ### БЛОК 1: Скачивание данных из API и сохранение в SQLite
# *(Запускайте этот блок, только когда нужно обновить данные из интернета)*

print(f"Начало сбора данных из API ENTSO-E...")

# Инициализация клиента (замените токен при необходимости)
client = EntsoePandasClient(api_key="71dbea05-02be-4d8d-9adf-95d5b7df8a17")

start = pd.Timestamp('2026-10-01', tz='Europe/Paris')
end = pd.Timestamp('2026-10-02', tz='Europe/Paris')

queries = {
    "Load and Forecast": lambda: client.query_load_and_forecast(COUNTRY_CODE, start=start, end=end),
    "Generation Forecast": lambda: client.query_generation_forecast(COUNTRY_CODE, start=start, end=end),
}

conn = sqlite3.connect(DB_NAME)

for name, query_func in queries.items():
    print(f"Запрос к API: {name}...")
    try:
        df = query_func()
        if df is not None and not df.empty:
            if isinstance(df, pd.Series):
                df = df.to_frame(name=name)
            
            df_to_save = df.copy()
            df_to_save = df_to_save.reset_index()
            df_to_save.columns.values[0] = 'timestamp'
            
            # Приведение названий колонок к строкам
            df_to_save.columns = [str(col) if not isinstance(col, tuple) else "_".join(map(str, col)) for col in df_to_save.columns]
            df_to_save['timestamp'] = df_to_save['timestamp'].astype(str)

            table_name = name.replace(" ", "_").lower()
            df_to_save.to_sql(table_name, conn, if_exists='replace', index=False)
            
            print(f"-> Записано в таблицу '{table_name}'. Строк: {len(df_to_save)}")
        else:
            print("-> Результат пуст.")
    except Exception as e:
        print(f"-> Ошибка при выполнении/записи: {e}")
        
conn.close()
print("Загрузка в SQLite успешно завершена!\n")


# %% [markdown]
# ### БЛОК 2: Чтение данных из SQLite и построение графика Plotly
# *(Этот блок можно запускать сколько угодно раз отдельно. Интернет не требуется)*

print(f"Читаем сохраненные данные из файла: {DB_NAME}")

expected_tables = {
    "Load and Forecast": "load_and_forecast",
    "Generation Forecast": "generation_forecast",
    "Wind & Solar Forecast": "wind_solar_forecast",
    "Actual Generation": "actual_generation"
}

successful_dfs = {}

if not os.path.exists(DB_NAME):
    print(f"Ошибка: Файл базы данных '{DB_NAME}' отсутствует. Сначала запустите Блок 1.")
else:
    conn = sqlite3.connect(DB_NAME)
    
    for client_name, table_name in expected_tables.items():
        try:
            table_check = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';").fetchone()
            if not table_check:
                continue
                
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                successful_dfs[client_name] = df
                print(f"-> Успешно загружен датасет '{client_name}' из таблицы '{table_name}'")
        except Exception as e:
            print(f"-> Ошибка чтения таблицы {table_name}: {e}")
            
    conn.close()

if not successful_dfs:
    print("\nВ базе данных нет доступных таблиц для вывода графика.")
else:
    print("\nОтрисовка интерактивного графика...")
    fig = go.Figure()
    right_axis_clients = ["Wind & Solar Forecast", "Actual Generation"]

    for client_name, df in successful_dfs.items():
        yaxis_target = "y2" if client_name in right_axis_clients else "y1"
        axis_suffix = " (Правая ось)" if client_name in right_axis_clients else ""

        for column in df.columns:
            label_name = f"{client_name} - {column}{axis_suffix}" if len(df.columns) > 1 and column != client_name else f"{client_name}{axis_suffix}"

            fig.add_trace(go.Scatter(
                x=df.index,
                y=df[column],
                mode='lines+markers',
                name=label_name,
                yaxis=yaxis_target,
                marker=dict(size=4, opacity=0.8),
                hovertemplate='<b>%{hovertext}</b><br>Время: %{x}<br>Значение: %{y:.2f} MW<extra></extra>',
                hovertext=[label_name] * len(df)
            ))

    fig.update_layout(
        title="Данные ENTSO-E для Франции (Локальный запуск из ALL_DB)",
        xaxis_title="Дата и время",
        yaxis=dict(title=dict(text="Мощность нагрузки (Левая ось, MW)", font=dict(color="#1f77b4")), tickfont=dict(color="#1f77b4")),
        yaxis2=dict(title=dict(text="Генерация / Прогноз RE (Правая ось, MW)", font=dict(color="#ff7f0e")), tickfont=dict(color="#ff7f0e"), anchor="x", overlaying="y", side="right"),
        hovermode="x unified",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="left", x=0)
    )

    fig.show()
