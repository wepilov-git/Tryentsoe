import os
import pandas as pd
from entsoe import EntsoePandasClient
from entsoe.mappings import Area

# Настройка полного отображения таблиц в консоли
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.width', 1000)

# Переходим в рабочую директорию
os.chdir('/storage/emulated/0/1')

# 1. Ваш рабочий API-ключ ENTSO-E
API_KEY = "71dbea05-02be-4d8d-9adf-95d5b7df8a17"

# 2. Инициализируем клиента
client = EntsoePandasClient(api_key=API_KEY)

# 3. Задаем временной интервал (ноябрь 2026)
start = pd.Timestamp("2026-11-01", tz="Europe/Berlin")
end = pd.Timestamp("2026-11-08", tz="Europe/Berlin")

# 4. Контрольные зоны TSO Германии
tso_zones = {
    "Amprion": Area.DE_AMPRION,
    "TenneT": Area.DE_TENNET,
    "50Hertz": Area.DE_50HZ,
    "TransnetBW": Area.DE_TRANSNET
}

# 5. Собираем данные
all_data = {}

for tso_name, zone in tso_zones.items():
    print(f"Выгрузка данных для {tso_name}...")
    try:
        # Запрос Actual Total Load
        res = client.query_load(zone, start=start, end=end)
        
        if res is not None and not res.empty:
            if isinstance(res, pd.Series):
                res = res.to_frame(name=tso_name)
            else:
                res.columns = [f"{tso_name}_{col}" for col in res.columns]
            
            # Если у TSO часовой шаг, приводим к 15 минутам (Forward Fill)
            current_freq = pd.infer_freq(res.index)
            if current_freq and ('H' in current_freq or 'h' in current_freq):
                res = res.resample('15min').ffill()
                
            all_data[tso_name] = res
        else:
            print(f"Предупреждение: Пустой ответ для {tso_name}")
            
    except Exception as e:
        print(f"Ошибка при выгрузке {tso_name}: {e}")

# 6. Вывод таблицы в консоль
if all_data:
    # Объединяем в единую 15-минутную сетку
    df = pd.concat(all_data.values(), axis=1)
    df = df.ffill().bfill()
    
    print("\n" + "="*50)
    print(" ДАННЫЕ ПОТРЕБЛЕНИЯ ГЕРМАНИИ ПО TSO (MW)")
    print("="*50)
    print(df)
else:
    print("\nНе удалось получить данные ни от одного TSO.")
