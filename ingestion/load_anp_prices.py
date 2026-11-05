"""
Incremental load of retail fuel prices collected by ANP (Brazil's National Petroleum Agency)
into `raw.anp_fuel_prices`.

ANP publishes one CSV per month and product group at
https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/serie-historica-de-precos-de-combustiveis
File names are not stable (2026 alone has `01-dados-abertos-precos-...`, `02-cados-abertos-...`,
`06-dados-abertos-precos-2026-06-...`, `10-diesel-gnv.csv`), and some months are missing.
So instead of hardcoding URLs, this script:

  1. reads the ANP page and discovers every monthly file for the product groups we need;
  2. infers year and month from the URL, whatever the naming pattern;
  3. downloads only files not in `raw.anp_files_loaded` (manifest), keeping a local cache;
  4. keeps only the state we operate in, and quarantines malformed rows instead of failing.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

import duckdb
import requests

PAGE = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/serie-historica-de-precos-de-combustiveis"
PRODUCT_GROUPS = ("diesel-gnv", "gasolina-etanol")
FIRST_YEAR = 2025
STATE = "RS"
KNOWN_PRODUCTS = ("DIESEL S10", "DIESEL", "GASOLINA", "GASOLINA ADITIVADA", "ETANOL", "GNV")

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "warehouse.duckdb"
CACHE = ROOT / ".cache" / "anp"

LINK = re.compile(r'href="(https://www\.gov\.br/anp/[^"]+/shpc/dsan/(\d{4})/([^"/]+\.csv))"')
MONTH_IN_NAME = re.compile(r"(?:^|[-_])(0[1-9]|1[0-2])(?=[-_.])")


def discover_files() -> list[dict]:
    html = get(PAGE).text
    files = {}
    for url, year, name in LINK.findall(html):
        group = next((g for g in PRODUCT_GROUPS if g.replace("-", "") in name.replace("-", "")), None)
        month = MONTH_IN_NAME.search(name.replace(year, ""))  # drop the year so '2026-06' does not confuse the month
        if group and month and int(year) >= FIRST_YEAR:
            files[url] = {"url": url, "year": int(year), "month": int(month.group(1)), "product_group": group}
    return sorted(files.values(), key=lambda f: (f["year"], f["month"], f["product_group"]))


def get(url: str, attempts: int = 4) -> requests.Response:
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            if attempt == attempts:
                raise
            print(f"  attempt {attempt} failed ({exc}); retrying")
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def download(file: dict) -> Path:
    target = CACHE / f"{file['year']}-{file['month']:02d}-{file['product_group']}.csv"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(get(file["url"]).content)
    return target


def main() -> None:
    con = duckdb.connect(str(WAREHOUSE))
    con.execute("create schema if not exists raw")
    con.execute("""create table if not exists raw.anp_fuel_prices (
        state varchar, municipality varchar, station_cnpj varchar, product varchar,
        collected_on varchar, sale_price varchar, unit varchar, brand varchar,
        source_year integer, source_month integer, source_file varchar)""")
    con.execute("""create table if not exists raw.anp_files_loaded (
        url varchar primary key, source_year integer, source_month integer, product_group varchar,
        rows_loaded integer, rows_quarantined integer, loaded_at timestamp)""")

    loaded = {r[0] for r in con.execute("select url from raw.anp_files_loaded").fetchall()}
    files = discover_files()
    pending = [f for f in files if f["url"] not in loaded]
    months = sorted({(f["year"], f["month"]) for f in files})
    print(f"ANP: {len(files)} files found ({months[0][0]}-{months[0][1]:02d} to {months[-1][0]}-{months[-1][1]:02d}); {len(pending)} new")

    for f in pending:
        path = download(f)
        state_rows = con.execute("""
            select trim("Estado - Sigla") as state, trim("Municipio") as municipality,
                   trim("CNPJ da Revenda") as station_cnpj, trim("Produto") as product,
                   "Data da Coleta" as collected_on, "Valor de Venda" as sale_price,
                   "Unidade de Medida" as unit, "Bandeira" as brand
            from read_csv(?, delim=';', header=true, all_varchar=true, null_padding=true, ignore_errors=true)
            where trim("Estado - Sigla") = ?""", [str(path), STATE]).fetchall()
        good = [r for r in state_rows if r[3] in KNOWN_PRODUCTS]
        quarantined = len(state_rows) - len(good)
        con.executemany(
            "insert into raw.anp_fuel_prices values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(*r, f["year"], f["month"], f["url"]) for r in good],
        )
        con.execute(
            "insert into raw.anp_files_loaded values (?, ?, ?, ?, ?, ?, ?)",
            [f["url"], f["year"], f["month"], f["product_group"], len(good), quarantined, datetime.now()],
        )
        print(f"  {f['year']}-{f['month']:02d} {f['product_group']:<16} {len(good):>5} {STATE} rows, {quarantined} quarantined")

    total = con.execute("select count(*) from raw.anp_fuel_prices").fetchone()[0]
    print(f"ANP: {total:,} {STATE} price observations in warehouse")
    con.close()


if __name__ == "__main__":
    main()
