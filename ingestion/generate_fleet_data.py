"""
Generate the fleet app extract (vehicles, drivers, fuelings) for a fictional logistics
company operating in Rio Grande do Sul, and load it into `raw`.

Prices paid are built on top of the REAL market prices loaded from ANP, so the fleet cost
moves with the actual diesel market (including the March 2026 jump). Stations are fictional:
this project never labels a real station as expensive.

Planted, as in real fleet data:
  - duplicate submissions (driver taps "send" twice: new id, same fueling)
  - odometer typos (recorded value lower than the previous one)
  - liters above tank capacity (fuel going into jerrycans)
  - wrong product for the vehicle
  - one station that charges well above the city's market price
  - one truck whose consumption deteriorates for four months (fuel diversion)

Run `load_anp_prices.py` first.
"""

from __future__ import annotations

import csv
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

SEED = 7
ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "warehouse.duckdb"
START, END = date(2025, 1, 1), date(2026, 10, 31)

# Fleet app writes city names in mixed case; ANP uses upper case.
BASES = ["Santa Cruz do Sul", "Porto Alegre", "Lajeado", "Santa Maria", "Pelotas", "Novo Hamburgo"]
FLEET = [("HT-6X2", 14), ("LT-34", 10), ("VAN-L", 8), ("CAR-FLEX", 4)]
MONTHLY_KM = {"heavy_truck": 9_000, "light_truck": 5_000, "van": 4_000, "car": 2_500}
APP_PRODUCT = {"diesel": "Diesel S10", "flex": "Gasolina comum"}
ANP_PRODUCT = {"Diesel S10": "DIESEL S10", "Gasolina comum": "GASOLINA"}

DIVERTING_VEHICLE = "SUL1H07"
DIVERSION_WINDOW = (date(2026, 5, 1), date(2026, 8, 31))
EXPENSIVE_STATION = "Posto Rota Pelotas 2"


def load_models() -> dict:
    with open(ROOT / "seeds" / "vehicle_models.csv", newline="") as f:
        return {r["vehicle_model"]: r for r in csv.DictReader(f)}


def market_medians(con) -> dict:
    """Median ANP price per (CITY, year-month, product). Missing months reuse the last known one."""
    rows = con.execute("""
        select upper(municipality), source_year, source_month, product,
               median(replace(sale_price, ',', '.')::double)
        from raw.anp_fuel_prices
        where product in ('DIESEL S10', 'GASOLINA')
        group by all""").fetchall()
    return {(c, y, m, p): v for c, y, m, p, v in rows}


def price_for(medians: dict, city: str, day: date, product: str) -> float:
    y, m = day.year, day.month
    for _ in range(6):  # walk back to the last month ANP published
        key = (city.upper(), y, m, product)
        if key in medians:
            return medians[key]
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    raise KeyError(f"no ANP price for {city} {day} {product}")


def main() -> None:
    rng = random.Random(SEED)
    models = load_models()
    con = duckdb.connect(str(WAREHOUSE))
    medians = market_medians(con)

    vehicles, drivers, fuelings = [], [], []
    stations = {city: {f"Posto Rota {city} {i}": rng.uniform(0.975, 1.035) for i in (1, 2, 3)} for city in BASES}
    stations["Pelotas"][EXPENSIVE_STATION] = 1.12

    n = 0
    for model, count in FLEET:
        spec = models[model]
        for _ in range(count):
            n += 1
            plate = f"SUL1{spec['vehicle_class'][0].upper()}{n:02d}"
            base = BASES[n % len(BASES)]
            vehicles.append((plate, model, base, rng.randint(2018, 2024)))
            drivers.append((f"D{n:02d}", f"Driver {n:02d}", base))

    for plate, model, base, _ in vehicles:
        spec = models[model]
        tank, bench = float(spec["tank_capacity_l"]), float(spec["benchmark_km_per_l"])
        daily_km = MONTHLY_KM[spec["vehicle_class"]] / 22
        app_product = APP_PRODUCT[spec["fuel_type"]]
        driver = f"D{int(plate[-2:]):02d}"
        odometer = rng.randint(40_000, 300_000)
        fuel = tank * rng.uniform(0.5, 0.9)
        last_odometer_recorded = odometer
        day = START
        while day <= END:
            if day.weekday() < 6:  # Monday to Saturday
                km = daily_km * rng.uniform(0.6, 1.4)
                efficiency = bench * rng.uniform(0.92, 1.06)
                burned = km / efficiency
                diverting = plate == DIVERTING_VEHICLE and DIVERSION_WINDOW[0] <= day <= DIVERSION_WINDOW[1]
                odometer += int(km)
                fuel = max(fuel - burned, tank * 0.05)  # drivers refuel before running dry
                if fuel < tank * rng.uniform(0.2, 0.35):
                    city = base if rng.random() < 0.7 else rng.choice(BASES)
                    station, factor = rng.choice(list(stations[city].items()))
                    liters = tank - fuel
                    if diverting:
                        liters *= 1.45  # paid for, never reached the tank
                    recorded_product = app_product
                    if rng.random() < 0.012:
                        liters = tank * rng.uniform(1.10, 1.30)  # jerrycans
                    if spec["fuel_type"] == "diesel" and rng.random() < 0.004:
                        recorded_product = "Gasolina comum"
                    recorded_odometer = odometer
                    if rng.random() < 0.008:
                        recorded_odometer = last_odometer_recorded - rng.randint(50, 900)  # typo
                    price = round(price_for(medians, city, day, ANP_PRODUCT[recorded_product]) * factor * rng.uniform(0.99, 1.01), 2)
                    liters = round(liters, 2)
                    fueled_at = datetime(day.year, day.month, day.day, rng.randint(6, 21), rng.randint(0, 59))
                    row = (str(uuid.UUID(int=rng.getrandbits(128))), plate, driver, fueled_at.isoformat(), city,
                           station, recorded_product, liters, price, round(liters * price, 2), recorded_odometer)
                    fuelings.append(row)
                    if rng.random() < 0.01:  # double submission: new id, same fueling
                        fuelings.append((str(uuid.UUID(int=rng.getrandbits(128))), *row[1:]))
                    if recorded_odometer == odometer:
                        last_odometer_recorded = odometer
                    fuel = tank
            day += timedelta(days=1)

    con.execute("create schema if not exists raw")
    con.execute("create or replace table raw.fleet_vehicles (plate varchar, vehicle_model varchar, home_base varchar, model_year integer)")
    con.executemany("insert into raw.fleet_vehicles values (?, ?, ?, ?)", vehicles)
    con.execute("create or replace table raw.fleet_drivers (driver_id varchar, driver_name varchar, home_base varchar)")
    con.executemany("insert into raw.fleet_drivers values (?, ?, ?)", drivers)
    con.execute("""create or replace table raw.fleet_fuelings (
        fueling_id varchar, plate varchar, driver_id varchar, fueled_at varchar, city varchar,
        station_name varchar, product varchar, liters double, unit_price double, total_paid double,
        odometer_km integer)""")
    con.executemany("insert into raw.fleet_fuelings values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", fuelings)
    print(f"Fleet app extract loaded: {len(vehicles)} vehicles, {len(fuelings):,} fuelings ({START} to {END})")
    con.close()


if __name__ == "__main__":
    main()
