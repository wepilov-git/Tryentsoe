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

# 4. Распределение TSO / стран по трем климатическим зонам
climatic_zones = {
    "Mediterranean": {
        "Spain": Area.ES,
        "Italy": Area.IT,
        "Greece": Area.GR,
        "Slovenia": Area.SI,
        "Croatia": Area.HR,
        "Albania": Area.AL,
        "Portugal": Area.PT
    },
    "Atlantic": {
        "Amprion": Area.DE_AMPRION,
        "TenneT": Area.DE_TENNET,
        "TransnetBW": Area.DE_TRANSNET,
        "France": Area.FR,
        "Netherlands": Area.NL,
        "Belgium": Area.BE,
        "Ireland": Area.IE,
        "Austria": Area.AT,
        "Switzerland": Area.CH,
        "Denmark": Area.DK,
        "Norway": Area.NO,
        "Sweden": Area.SE
    },
    "Eastern": {
        "50Hertz": Area.DE_50HZ,
        "Poland": Area.PL,
        "Hungary": Area.HU,
        "Romania": Area.RO,
        "Bulgaria": Area.BG,
        "Estonia": Area.EE,
        "Latvia": Area.LV,
        "Lithuania": Area.LT,
        "CzechRepublic": Area.CZ,
        "Slovakia": Area.SK,
        "Finland": Area.FI
    }
}

# 5. Собираем данные по зонам
zone_dataframes = {}

for zone_name, tso_zones in climatic_zones.items():
    print(f"\n--- Выгрузка данных для зоны: {zone_name} ---")
    all_data_zone = {}
    
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
                
                # Приведение к единой 15-минутной сетке методом Forward Fill
                res = res.resample('15min').ffill()
                all_data_zone[tso_name] = res
            else:
                print(f"Предупреждение: Пустой ответ для {tso_name}")
        except Exception as e:
            print(f"Ошибка при выгрузке {tso_name}: {e}")
            
    # Объединяем данные внутри одной зоны
    if all_data_zone:
        df_zone = pd.concat(all_data_zone.values(), axis=1)
        df_zone = df_zone.ffill().bfill()
        zone_dataframes[zone_name] = df_zone

# 6. Вывод таблиц в консоль по климатическим зонам
if zone_dataframes:
    for zone_name, df in zone_dataframes.items():
        print("\n" + "="*60)
        print(f" ДАННЫЕ ПОТРЕБЛЕНИЯ ЗОНЫ: {zone_name.upper()} (MW)")
        print("="*60)
        print(df)
else:
    print("\nНе удалось получить данные ни от одного TSO.")
