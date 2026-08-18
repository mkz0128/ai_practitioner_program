from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha1
from pathlib import Path

import duckdb

from generate_auction_lots import AUCTION_HOUSES, DB_PATH, EXPORT_DIR, PROJECT_ROOT


HKMA_ENDPOINT = (
    "https://api.hkma.gov.hk/public/market-data-and-statistics/"
    "monthly-statistical-bulletin/er-ir/er-eeri-daily"
)
RAW_FX_PATH = PROJECT_ROOT / "data" / "raw" / "hkma" / "exchange_rates_2019_2025.json"
FX_START = date(2020, 1, 1)
FX_END = date(2025, 12, 31)
FETCH_START = date(2019, 12, 1)
FX_CURRENCIES = ("USD", "HKD", "GBP", "EUR", "JPY", "TWD")


HOUSE_ALIASES: dict[str, tuple[str, ...]] = {
    "SOT": ("蘇富比", "蘇富比拍賣", "香港蘇富比", "Sotheby's", "Sothebys"),
    "CHR": ("佳士得", "佳士得拍賣", "香港佳士得", "Christie's", "Christies"),
    "BON": ("邦瀚斯", "邦瀚斯拍賣", "香港邦瀚斯", "Bonhams"),
    "CGD": ("中國嘉德", "中國嘉德拍賣", "嘉德", "嘉德拍賣"),
    "CGH": ("中國嘉德（香港）", "中國嘉德(香港)", "中國嘉德香港", "嘉德香港"),
    "BPL": ("北京保利", "北京保利拍賣", "保利北京"),
    "PHK": ("保利香港", "保利香港拍賣", "香港保利"),
    "YON": ("永樂拍賣", "北京永樂", "永樂"),
    "XLY": ("西泠印社", "西泠印社拍賣", "西泠拍賣"),
    "HYG": ("華藝國際（廣州）", "華藝國際(廣州)", "廣州華藝國際", "華藝國際"),
    "TCA": ("東京中央", "東京中央拍賣"),
    "TFA": ("東京飛鳥", "東京飛鳥拍賣"),
    "YIA": ("橫濱國拍", "橫濱國際拍賣", "橫濱國際"),
    "DIT": ("帝圖", "帝圖藝術拍賣", "帝圖拍賣"),
    "YZH": ("宇珍", "宇珍國際藝術", "宇珍拍賣"),
}


def fetch_hkma_records() -> list[dict]:
    if RAW_FX_PATH.exists():
        with RAW_FX_PATH.open("r", encoding="utf-8") as stream:
            return json.load(stream)["records"]

    records: list[dict] = []
    offset = 0
    page_size = 1000
    reached_start = False
    while not reached_start:
        query = urllib.parse.urlencode({"pagesize": page_size, "offset": offset})
        request = urllib.request.Request(
            f"{HKMA_ENDPOINT}?{query}",
            headers={"User-Agent": "AuctionAgentDemo/1.0"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.load(response)
        if not payload.get("header", {}).get("success"):
            raise RuntimeError(f"HKMA API error: {payload.get('header')}")
        batch = payload.get("result", {}).get("records", [])
        if not batch:
            break
        records.extend(batch)
        oldest = min(date.fromisoformat(row["end_of_day"]) for row in batch)
        reached_start = oldest <= FETCH_START
        offset += len(batch)

    selected = [
        row
        for row in records
        if FETCH_START <= date.fromisoformat(row["end_of_day"]) <= FX_END
    ]
    selected.sort(key=lambda row: row["end_of_day"])
    if not selected or date.fromisoformat(selected[0]["end_of_day"]) > FX_START:
        raise RuntimeError("HKMA history does not contain a rate on or before 2020-01-01")

    RAW_FX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RAW_FX_PATH.open("w", encoding="utf-8") as stream:
        json.dump(
            {
                "source": "Hong Kong Monetary Authority",
                "source_url": HKMA_ENDPOINT,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "records": selected,
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
    return selected


def build_exchange_rate_rows(records: list[dict]) -> list[dict]:
    source_by_date = {
        date.fromisoformat(row["end_of_day"]): row
        for row in records
        if row.get("cny") not in (None, 0)
    }
    available_dates = sorted(source_by_date)
    source_index = 0
    latest_date: date | None = None
    rows: list[dict] = []
    current = FX_START
    while current <= FX_END:
        while source_index < len(available_dates) and available_dates[source_index] <= current:
            latest_date = available_dates[source_index]
            source_index += 1
        if latest_date is None:
            raise RuntimeError(f"No HKMA rate available on or before {current}")
        source = source_by_date[latest_date]
        cny_hkd = Decimal(str(source["cny"]))
        for currency in FX_CURRENCIES:
            source_hkd = Decimal("1") if currency == "HKD" else Decimal(str(source[currency.lower()]))
            rows.append(
                {
                    "rate_date": current,
                    "source_date": latest_date,
                    "from_currency": currency,
                    "to_currency": "RMB",
                    "rate_to_rmb": (source_hkd / cny_hkd).quantize(Decimal("0.0000000001")),
                    "source_hkd_per_unit": source_hkd,
                    "cny_hkd_per_unit": cny_hkd,
                    "is_carried_forward": current != latest_date,
                    "source_name": "香港金融管理局",
                    "source_url": HKMA_ENDPOINT,
                }
            )
        current += timedelta(days=1)
    return rows


def build_house_rows() -> list[dict]:
    return [
        {
            "auction_house_id": code,
            "auction_house_name": name,
            "main_city": city,
            "country_region": country,
        }
        for code, name, city, country in AUCTION_HOUSES
    ]


def build_event_rows(connection: duckdb.DuckDBPyConnection) -> list[dict]:
    source_rows = connection.execute(
        """
        SELECT DISTINCT event_id, auction_house_id, category, auction_house,
                        auction_event, auction_date, auction_location
        FROM auction_lots
        ORDER BY auction_date, auction_house, category, auction_event
        """
    ).fetchall()
    rows = []
    seen_ids: set[str] = set()
    for event_id, house_id, category, house, event, event_date, location in source_rows:
        if event_id in seen_ids:
            raise RuntimeError(f"Duplicate generated event ID: {event_id}")
        seen_ids.add(event_id)
        rows.append(
            {
                "event_id": event_id,
                "auction_house_id": house_id,
                "auction_event": event,
                "auction_date": event_date,
                "auction_location": location,
                "category": category,
                "data_status": "模擬",
            }
        )
    return rows


def build_alias_rows() -> list[dict]:
    canonical_by_code = {code: name for code, name, _, _ in AUCTION_HOUSES}
    rows = []
    for code, aliases in HOUSE_ALIASES.items():
        canonical = canonical_by_code[code]
        for alias in aliases:
            raw_key = f"auction_house|{alias}|{canonical}"
            rows.append(
                {
                    "alias_id": "ALS-" + sha1(raw_key.encode("utf-8")).hexdigest()[:12].upper(),
                    "entity_type": "auction_house",
                    "alias_name": alias,
                    "canonical_name": canonical,
                    "auction_house_id": code,
                    "language": "en" if alias.isascii() else "zh",
                }
            )
    return rows


def insert_rows(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    columns: tuple[str, ...],
    rows: list[dict],
) -> None:
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        [[row[column] for column in columns] for row in rows],
    )


def write_tables(
    house_rows: list[dict],
    event_rows: list[dict],
    alias_rows: list[dict],
    fx_rows: list[dict],
) -> None:
    connection = duckdb.connect(str(DB_PATH))
    for table in ("name_aliases", "auction_events", "auction_houses", "exchange_rates"):
        connection.execute(f"DROP TABLE IF EXISTS {table}")

    connection.execute(
        """
        CREATE TABLE auction_houses (
            auction_house_id VARCHAR PRIMARY KEY,
            auction_house_name VARCHAR NOT NULL UNIQUE,
            main_city VARCHAR NOT NULL,
            country_region VARCHAR NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE auction_events (
            event_id VARCHAR PRIMARY KEY,
            auction_house_id VARCHAR NOT NULL REFERENCES auction_houses(auction_house_id),
            auction_event VARCHAR NOT NULL,
            auction_date DATE NOT NULL,
            auction_location VARCHAR NOT NULL,
            category VARCHAR NOT NULL,
            data_status VARCHAR NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE name_aliases (
            alias_id VARCHAR PRIMARY KEY,
            entity_type VARCHAR NOT NULL,
            alias_name VARCHAR NOT NULL,
            canonical_name VARCHAR NOT NULL,
            auction_house_id VARCHAR NOT NULL REFERENCES auction_houses(auction_house_id),
            language VARCHAR NOT NULL,
            UNIQUE(entity_type, alias_name)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE exchange_rates (
            rate_date DATE NOT NULL,
            source_date DATE NOT NULL,
            from_currency VARCHAR NOT NULL,
            to_currency VARCHAR NOT NULL,
            rate_to_rmb DECIMAL(20, 10) NOT NULL,
            source_hkd_per_unit DECIMAL(20, 10) NOT NULL,
            cny_hkd_per_unit DECIMAL(20, 10) NOT NULL,
            is_carried_forward BOOLEAN NOT NULL,
            source_name VARCHAR NOT NULL,
            source_url VARCHAR NOT NULL,
            PRIMARY KEY(rate_date, from_currency, to_currency)
        )
        """
    )

    insert_rows(connection, "auction_houses", tuple(house_rows[0]), house_rows)
    insert_rows(connection, "auction_events", tuple(event_rows[0]), event_rows)
    insert_rows(connection, "name_aliases", tuple(alias_rows[0]), alias_rows)
    insert_rows(connection, "exchange_rates", tuple(fx_rows[0]), fx_rows)
    connection.execute("CREATE INDEX idx_events_lookup ON auction_events(auction_date, auction_house_id)")
    connection.execute("CREATE INDEX idx_alias_lookup ON name_aliases(entity_type, alias_name)")
    connection.execute("CREATE INDEX idx_fx_lookup ON exchange_rates(rate_date, from_currency)")
    connection.close()


def export_csv(name: str, rows: list[dict]) -> None:
    with (EXPORT_DIR / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_and_export() -> None:
    connection = duckdb.connect(str(DB_PATH), read_only=True)
    checks = (
        ("auction_houses_rows", "SELECT COUNT(*) FROM auction_houses", 15),
        ("auction_events_orphans", "SELECT COUNT(*) FROM auction_events e ANTI JOIN auction_houses h USING(auction_house_id)", 0),
        ("auction_lot_event_id_orphans", "SELECT COUNT(*) FROM auction_lots l ANTI JOIN auction_events e USING(event_id)", 0),
        ("auction_lot_house_id_orphans", "SELECT COUNT(*) FROM auction_lots l ANTI JOIN auction_houses h USING(auction_house_id)", 0),
        ("event_house_id_mismatch", "SELECT COUNT(*) FROM auction_lots l JOIN auction_events e USING(event_id) WHERE l.auction_house_id <> e.auction_house_id", 0),
        ("auction_events_unmatched_lots", """
            SELECT COUNT(*) FROM auction_lots l
            WHERE NOT EXISTS (
                SELECT 1 FROM auction_events e JOIN auction_houses h USING(auction_house_id)
                WHERE e.category=l.category AND h.auction_house_name=l.auction_house
                  AND e.auction_event=l.auction_event AND e.auction_date=l.auction_date
                  AND e.auction_location=l.auction_location
            )
        """, 0),
        ("name_alias_duplicates", "SELECT COUNT(*)-COUNT(DISTINCT entity_type || '|' || alias_name) FROM name_aliases", 0),
        ("exchange_rate_rows", "SELECT COUNT(*) FROM exchange_rates", 13_152),
        ("exchange_rate_dates", "SELECT COUNT(DISTINCT rate_date) FROM exchange_rates", 2_192),
        ("exchange_rate_currencies", "SELECT COUNT(DISTINCT from_currency) FROM exchange_rates", 6),
        ("exchange_rate_invalid", "SELECT COUNT(*) FROM exchange_rates WHERE rate_to_rmb <= 0 OR source_date > rate_date", 0),
        ("carried_flag_mismatch", "SELECT COUNT(*) FROM exchange_rates WHERE is_carried_forward <> (source_date <> rate_date)", 0),
        ("auction_event_fx_missing", """
            SELECT COUNT(*) FROM auction_events e
            CROSS JOIN (VALUES ('USD'), ('HKD'), ('GBP'), ('EUR'), ('JPY'), ('TWD')) c(currency)
            LEFT JOIN exchange_rates x
              ON x.rate_date=e.auction_date AND x.from_currency=c.currency AND x.to_currency='RMB'
            WHERE x.rate_date IS NULL
        """, 0),
    )
    results = []
    for name, sql, expected in checks:
        actual = connection.execute(sql).fetchone()[0]
        results.append((name, actual, expected, actual == expected))
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("auction_lots", "auction_events", "auction_houses", "exchange_rates", "name_aliases")
    }
    connection.close()
    if not all(row[3] for row in results):
        raise AssertionError(f"Reference-table validation failed: {results}")
    with (EXPORT_DIR / "reference_tables_validation.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("check", "actual", "expected", "passed"))
        writer.writerows(results)
    print("Table rows:", ", ".join(f"{table}={count:,}" for table, count in counts.items()))


def main() -> None:
    records = fetch_hkma_records()
    fx_rows = build_exchange_rate_rows(records)
    house_rows = build_house_rows()
    connection = duckdb.connect(str(DB_PATH), read_only=True)
    event_rows = build_event_rows(connection)
    connection.close()
    alias_rows = build_alias_rows()
    write_tables(house_rows, event_rows, alias_rows, fx_rows)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export_csv("auction_houses", house_rows)
    export_csv("auction_events", event_rows)
    export_csv("name_aliases", alias_rows)
    export_csv("exchange_rates", fx_rows)
    validate_and_export()


if __name__ == "__main__":
    main()
