from __future__ import annotations

import csv
import json
import math
import random
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha1
from pathlib import Path

import duckdb


SEED = 20200812
ROWS_PER_CATEGORY = 3_000
YEARS = list(range(2020, 2026))
ROWS_PER_YEAR = 2_500
CURRENCY = "RMB"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "npm"
EXPORT_DIR = PROJECT_ROOT / "data" / "exports"
DB_PATH = PROJECT_ROOT / "data" / "auction_demo.duckdb"


@dataclass(frozen=True)
class CategorySpec:
    api_name: str
    category_zh: str
    event_titles: tuple[str, ...]
    median_rmb: int
    sigma: float


CATEGORIES = (
    CategorySpec(
        "bronzes",
        "銅器",
        ("中國古代青銅器藝術", "吉金永寶－重要青銅器", "中國藝術珍品－青銅器專場"),
        1_200_000,
        1.55,
    ),
    CategorySpec(
        "ceramics",
        "陶瓷器",
        ("重要中國瓷器及工藝精品", "御窯菁華－中國古代陶瓷", "中國藝術珍品－瓷器專場"),
        800_000,
        1.50,
    ),
    CategorySpec(
        "jades",
        "玉器",
        ("瑰麗玉器與宮廷藝術", "韞玉生輝－中國古代玉器", "中國藝術珍品－玉器專場"),
        650_000,
        1.45,
    ),
    CategorySpec(
        "paintings",
        "繪畫",
        ("中國古代書畫", "中國近現代書畫", "翰墨丹青－中國繪畫專場"),
        900_000,
        1.65,
    ),
    CategorySpec(
        "calligraphicWorks",
        "法書",
        ("中國古代書法", "翰墨流芳－歷代法書", "中國書畫珍藏"),
        700_000,
        1.55,
    ),
)

API_BASE = "https://odapi.npm.gov.tw/data/open/api/v1/digitalCollection"

AUCTION_HOUSES = (
    ("SOT", "蘇富比", "香港", "香港"),
    ("CHR", "佳士得", "香港", "香港"),
    ("BON", "邦瀚斯", "香港", "香港"),
    ("CGD", "中國嘉德", "北京", "中國"),
    ("CGH", "中國嘉德（香港）", "香港", "香港"),
    ("BPL", "北京保利", "北京", "中國"),
    ("PHK", "保利香港", "香港", "香港"),
    ("YON", "永樂拍賣", "北京", "中國"),
    ("XLY", "西泠印社", "杭州", "中國"),
    ("HYG", "華藝國際（廣州）", "廣州", "中國"),
    ("TCA", "東京中央", "東京", "日本"),
    ("TFA", "東京飛鳥", "東京", "日本"),
    ("YIA", "橫濱國拍", "橫濱", "日本"),
    ("DIT", "帝圖", "台北", "台灣"),
    ("YZH", "宇珍", "台北", "台灣"),
)

SCHEMA = (
    ("category", "VARCHAR", "拍品分類"),
    ("subcategory", "VARCHAR", "依品名規則整理的拍品細分類"),
    ("image_url", "VARCHAR", "拍品圖片網址"),
    ("title_zh", "VARCHAR", "中文品名"),
    ("era_or_artist", "VARCHAR", "年代或作者"),
    ("auction_house", "VARCHAR", "拍賣公司"),
    ("auction_event", "VARCHAR", "拍賣場次"),
    ("auction_date", "DATE", "拍賣日期"),
    ("auction_location", "VARCHAR", "拍賣地區"),
    ("lot_number", "VARCHAR", "同一場次內的 Lot 編號"),
    ("size_text", "VARCHAR", "尺寸原文"),
    ("estimate_low", "BIGINT", "最低估價（RMB）"),
    ("estimate_high", "BIGINT", "最高估價（RMB）"),
    ("sold_price", "BIGINT", "成交價；流拍與撤拍為 NULL"),
    ("currency", "VARCHAR", "固定為 RMB"),
    ("sale_status", "VARCHAR", "成交 / 流拍 / 撤拍"),
    ("lot_id", "VARCHAR", "內部使用的拍品全域唯一識別碼"),
    ("event_id", "VARCHAR", "內部使用的拍賣場次識別碼"),
    ("auction_house_id", "VARCHAR", "內部使用的拍賣公司識別碼"),
    ("artist_name", "VARCHAR", "可靠解析出的作者；無法辨識時為 NULL"),
    ("era_name", "VARCHAR", "故宮原始年代；來源缺漏時為 NULL"),
    ("attribution_status", "VARCHAR", "已解析作者 / 僅有年代 / 資料不詳 / 需要確認"),
)

NULLABLE_COLUMNS = {"sold_price", "artist_name", "era_name"}


def download_json(spec: CategorySpec) -> list[dict]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / f"{spec.api_name}.json"
    if not target.exists():
        url = f"{API_BASE}/{spec.api_name}.json"
        request = urllib.request.Request(url, headers={"User-Agent": "AuctionAgentDemo/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            target.write_bytes(response.read())
    with target.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def deterministic_category_sample(items: list[dict], category: str) -> list[dict]:
    eligible = [
        item
        for item in items
        if item.get("identifier")
        and item.get("name")
        and item.get("imageUrl_m")
        and item.get("imageUrl_s")
        and item.get("url")
    ]
    if len(eligible) < ROWS_PER_CATEGORY:
        raise ValueError(f"{category} only has {len(eligible)} eligible objects")
    category_rng = random.Random(f"{SEED}:{category}")
    return category_rng.sample(eligible, ROWS_PER_CATEGORY)


def all_weekend_dates(year: int) -> list[date]:
    current = date(year, 1, 1)
    result: list[date] = []
    while current.year == year:
        if current.weekday() in (5, 6):
            result.append(current)
        current += timedelta(days=1)
    return result


def make_event_catalog(rng: random.Random) -> dict[tuple[int, str], list[dict]]:
    events: dict[tuple[int, str], list[dict]] = {}
    for year in YEARS:
        weekends = all_weekend_dates(year)
        for spec in CATEGORIES:
            category_events: list[dict] = []
            for house_index, (code, house, city, country) in enumerate(AUCTION_HOUSES):
                for cycle in range(2):
                    start_month = 3 if cycle == 0 else 9
                    end_month = 6 if cycle == 0 else 12
                    candidates = [d for d in weekends if start_month <= d.month <= end_month]
                    event_date = candidates[(house_index * 7 + cycle * 13 + year + rng.randrange(len(candidates))) % len(candidates)]
                    title = spec.event_titles[(house_index + cycle + year) % len(spec.event_titles)]
                    season = "春季" if cycle == 0 else "秋季"
                    event_id = f"SIM-{year}-{code}-{spec.api_name[:3].upper()}-{cycle + 1}"
                    category_events.append(
                        {
                            "event_id": event_id,
                            "event_name": f"{season} {title}（模擬場次）",
                            "event_date": event_date,
                            "house_code": code,
                            "house": house,
                            "city": city,
                            "country": country,
                        }
                    )
            events[(year, spec.category_zh)] = category_events
    return events


def rounded_price(value: float) -> int:
    value = max(10_000.0, min(value, 500_000_000.0))
    if value < 100_000:
        unit = 1_000
    elif value < 1_000_000:
        unit = 10_000
    elif value < 10_000_000:
        unit = 50_000
    else:
        unit = 100_000
    return int(round(value / unit) * unit)


def make_price(rng: random.Random, spec: CategorySpec, status: str) -> tuple[int, int, int | None]:
    low = rounded_price(rng.lognormvariate(math.log(spec.median_rmb), spec.sigma))
    high = rounded_price(low * rng.uniform(1.18, 1.75))
    if high <= low:
        high = low + max(10_000, int(low * 0.2))
    if status != "成交":
        return low, high, None
    outcome = rng.random()
    if outcome < 0.12:
        sold = rounded_price(low * rng.uniform(0.82, 0.99))
    elif outcome < 0.77:
        sold = rounded_price(rng.uniform(low, high))
    elif outcome < 0.97:
        sold = rounded_price(high * rng.uniform(1.01, 2.5))
    else:
        sold = rounded_price(high * rng.uniform(2.5, 8.0))
    return low, high, sold


def balanced_years_and_statuses(rng: random.Random) -> tuple[list[int], list[str]]:
    years = [year for year in YEARS for _ in range(ROWS_PER_YEAR)]
    statuses = ["成交"] * 12_000 + ["流拍"] * 2_550 + ["撤拍"] * 450
    rng.shuffle(years)
    rng.shuffle(statuses)
    return years, statuses


DYNASTY_PATTERN = (
    r"(?:民國|南朝梁|南朝|北宋|南宋|東晉|西晉|五代|清|明|元|宋|唐|隋|遼|金)"
)
AUTHOR_MARKERS = (
    r"(?:行草書|行楷書|行書|草書|楷書|隸書|篆書|寫經|手札|雜書|"
    r"四景|倣古|仿古|"
    r"畫|書|致|詩翰|詩|山水|花卉|墨竹|人物|真蹟|翰|札|函|聯)"
)
AUTHOR_PATTERN = re.compile(
    DYNASTY_PATTERN + r"(?P<name>[\u4e00-\u9fff]{2,4}?)(?=" + AUTHOR_MARKERS + r")"
)
INVALID_AUTHOR_TERMS = (
    "人",
    "名家",
    "當代",
    "諸家",
    "群賢",
    "帝后",
    "后妃",
    "御筆",
    "宮廷",
    "佚名",
    "無款",
    "書翰",
    "集繪",
    "扇頭",
    "便面",
)


def extract_author(title: str) -> str | None:
    """Extract only high-confidence named creators encoded in NPM titles."""
    normalized = re.sub(r"[\s　]+", "", title or "")
    for match in AUTHOR_PATTERN.finditer(normalized):
        candidate = match.group("name")
        if any(term in candidate for term in INVALID_AUTHOR_TERMS):
            continue
        if candidate.endswith(("繪", "畫", "書", "詩", "法", "山水", "花卉")):
            continue
        return candidate
    return None


SUBCATEGORY_RULES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "陶瓷器": (
        ("琺瑯彩", ("琺瑯彩",)),
        ("粉彩", ("粉彩",)),
        ("鬥彩", ("鬥彩",)),
        ("五彩", ("五彩",)),
        ("釉裡紅", ("釉裡紅", "釉裏紅")),
        ("青花", ("青花",)),
        ("汝窯", ("汝窯", "汝釉")),
        ("官窯", ("官窯", "官釉")),
        ("哥窯", ("哥窯", "哥釉")),
        ("鈞窯", ("鈞窯", "鈞釉")),
        ("定窯", ("定窯",)),
        ("龍泉窯", ("龍泉",)),
        ("青瓷／青釉", ("青瓷", "青釉", "天青釉", "冬青釉", "粉青釉")),
        ("白瓷／白釉", ("白瓷", "白釉", "甜白釉")),
        ("黃釉", ("黃釉",)),
        ("紅釉／紅彩", ("紅釉", "紅彩", "胭脂紅", "祭紅")),
        ("黑釉", ("黑釉", "烏金釉")),
        ("綠釉／綠彩", ("綠釉", "綠彩")),
        ("其他陶瓷", ()),
    ),
    "銅器": (
        ("鼎", ("鼎",)),
        ("尊", ("尊",)),
        ("爵／觚／觶", ("爵", "觚", "觶", "斝")),
        ("壺／瓶", ("壺", "瓶", "罍", "卣", "盉")),
        ("簋／簠／豆", ("簋", "簠", "豆")),
        ("盤／洗", ("盤", "洗", "匜")),
        ("鐘／樂器", ("鐘", "鍾", "鐃", "鈴", "磬")),
        ("銅鏡", ("鏡",)),
        ("銅印", ("印",)),
        ("佛教造像", ("佛", "菩薩", "羅漢", "造像")),
        ("兵器", ("劍", "刀", "戈", "矛", "鏃", "兵器")),
        ("其他銅器", ()),
    ),
    "玉器": (
        ("玉璧", ("璧",)),
        ("玉琮", ("琮",)),
        ("玉圭", ("圭",)),
        ("玉璜", ("璜",)),
        ("玉佩／玉飾", ("佩", "珮", "環", "飾", "墜", "腰結")),
        ("玉帶具", ("帶鉤", "帶扣", "帶板", "帶飾")),
        ("玉印", ("印",)),
        ("玉冊", ("玉冊",)),
        ("玉器皿", ("杯", "碗", "盤", "瓶", "壺", "盒", "洗", "筆筒")),
        ("玉雕", ("雕", "山子", "擺件", "像")),
        ("其他玉器", ()),
    ),
    "繪畫": (
        ("山水", ("山水", "山居", "溪山", "江山", "秋山", "雪景", "林泉")),
        ("花鳥", ("花鳥", "花卉", "牡丹", "梅", "蘭", "竹", "菊", "荷", "禽", "鳥")),
        ("人物", ("人物", "仕女", "羅漢", "佛", "觀音", "高士", "嬰戲", "肖像", "像")),
        ("走獸／蟲魚", ("走獸", "馬", "牛", "鹿", "虎", "貓", "犬", "魚", "蟲", "鷹")),
        ("其他繪畫", ()),
    ),
    "法書": (
        ("行草書", ("行草",)),
        ("行楷書", ("行楷",)),
        ("行書", ("行書",)),
        ("草書", ("草書",)),
        ("楷書", ("楷書", "正書")),
        ("隸書", ("隸書",)),
        ("篆書", ("篆書",)),
        ("書札／信函", ("書札", "尺牘", "致", "函", "信", "札")),
        ("寫經", ("寫經", "經卷", "經冊", "佛經")),
        ("法帖", ("法帖", "帖")),
        ("其他法書", ()),
    ),
}


def derive_subcategory(category: str, title: str) -> str:
    normalized = re.sub(r"[\s　]+", "", title or "")
    rules = SUBCATEGORY_RULES[category]
    for label, keywords in rules:
        if not keywords or any(keyword in normalized for keyword in keywords):
            return label
    raise AssertionError(f"No subcategory fallback for {category}")


def derive_era_or_artist(category: str, title: str, era: str) -> str:
    if category in {"繪畫", "法書"}:
        author = extract_author(title)
        if author:
            return author
    return (era or "").strip() or "不詳"


def derive_attribution(category: str, title: str, era: str) -> tuple[str | None, str | None, str]:
    """Keep the book-style field while exposing reliable analysis fields."""
    normalized_era = (era or "").strip()
    artist = extract_author(title) if category in {"繪畫", "法書"} else None
    era_name = normalized_era or None
    if artist:
        return artist, era_name, "已解析作者"
    if normalized_era in {"待訂", "時代待訂"} or "待訂" in normalized_era:
        return None, era_name, "需要確認"
    if not normalized_era or normalized_era == "不詳":
        return None, None, "資料不詳"
    return None, era_name, "僅有年代"


def make_lot_id(event_id: str, lot_number: str) -> str:
    """Generate a stable global ID from the event-local natural key."""
    digest = sha1(f"{event_id}|{lot_number}".encode("utf-8")).hexdigest()[:12].upper()
    return f"LOT-{digest}"


def generate_rows() -> list[dict]:
    rng = random.Random(SEED)
    events = make_event_catalog(rng)
    years, statuses = balanced_years_and_statuses(rng)
    selected: list[tuple[CategorySpec, dict]] = []
    for spec in CATEGORIES:
        selected.extend((spec, item) for item in deterministic_category_sample(download_json(spec), spec.category_zh))
    identifiers = [item["identifier"] for _, item in selected]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Selected NPM objects are not unique")
    rng.shuffle(selected)

    rows: list[dict] = []
    event_lot_counters: Counter[str] = Counter()
    for index, ((spec, item), year, status) in enumerate(zip(selected, years, statuses), start=1):
        category_events = events[(year, spec.category_zh)]
        event = category_events[rng.randrange(len(category_events))]
        event_lot_counters[event["event_id"]] += 1
        lot_number = f"{event_lot_counters[event['event_id']]:04d}"
        estimate_low, estimate_high, sold_price = make_price(rng, spec, status)
        artist_name, era_name, attribution_status = derive_attribution(
            spec.category_zh,
            item.get("name", ""),
            item.get("era", ""),
        )
        rows.append(
            {
                "category": spec.category_zh,
                "subcategory": derive_subcategory(spec.category_zh, item.get("name", "")),
                "image_url": item.get("imageUrl_m", ""),
                "title_zh": item.get("name", ""),
                "era_or_artist": derive_era_or_artist(
                    spec.category_zh,
                    item.get("name", ""),
                    item.get("era", ""),
                ),
                "auction_house": event["house"],
                "auction_event": event["event_name"],
                "auction_date": event["event_date"],
                "auction_location": event["city"],
                "lot_number": lot_number,
                "size_text": item.get("size", ""),
                "estimate_low": estimate_low,
                "estimate_high": estimate_high,
                "sold_price": sold_price,
                "currency": CURRENCY,
                "sale_status": status,
                "lot_id": make_lot_id(event["event_id"], lot_number),
                "event_id": event["event_id"],
                "auction_house_id": event["house_code"],
                "artist_name": artist_name,
                "era_name": era_name,
                "attribution_status": attribution_status,
            }
        )
    return rows


def write_database(rows: list[dict]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    connection = duckdb.connect(str(DB_PATH))
    column_sql = ",\n".join(
        f'    "{name}" {data_type}' + ("" if name in NULLABLE_COLUMNS else " NOT NULL")
        for name, data_type, _ in SCHEMA
    )
    connection.execute(f"CREATE TABLE auction_lots (\n{column_sql}\n)")
    columns = [name for name, _, _ in SCHEMA]
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO auction_lots VALUES ({placeholders})",
        [[row[column] for column in columns] for row in rows],
    )
    connection.execute("CREATE INDEX idx_auction_lots_image ON auction_lots(image_url)")
    connection.execute("CREATE INDEX idx_auction_lots_filters ON auction_lots(category, auction_date, sale_status)")
    connection.execute("CREATE INDEX idx_auction_lots_house ON auction_lots(auction_house)")
    connection.execute("CREATE UNIQUE INDEX idx_auction_lots_id ON auction_lots(lot_id)")
    connection.execute("CREATE UNIQUE INDEX idx_auction_lots_event_lot ON auction_lots(event_id, lot_number)")
    connection.close()


def write_exports(rows: list[dict]) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    columns = [name for name, _, _ in SCHEMA]
    with (EXPORT_DIR / "auction_lots.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    with (EXPORT_DIR / "auction_lots_sample.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows[:200])
    with (EXPORT_DIR / "auction_lots_schema.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["column_name", "data_type", "description"])
        writer.writerows(SCHEMA)


def validate_and_export() -> None:
    connection = duckdb.connect(str(DB_PATH), read_only=True)
    checks = [
        ("total_rows", "SELECT COUNT(*) FROM auction_lots", 15_000),
        ("categories", "SELECT COUNT(DISTINCT category) FROM auction_lots", 5),
        ("auction_houses", "SELECT COUNT(DISTINCT auction_house) FROM auction_lots", 15),
        ("sold_rows", "SELECT COUNT(*) FROM auction_lots WHERE sale_status='成交'", 12_000),
        ("unsold_rows", "SELECT COUNT(*) FROM auction_lots WHERE sale_status='流拍'", 2_550),
        ("withdrawn_rows", "SELECT COUNT(*) FROM auction_lots WHERE sale_status='撤拍'", 450),
        ("non_weekend_dates", "SELECT COUNT(*) FROM auction_lots WHERE dayofweek(auction_date) NOT IN (0, 6)", 0),
        ("missing_image_urls", "SELECT COUNT(*) FROM auction_lots WHERE image_url=''", 0),
        ("non_rmb_rows", "SELECT COUNT(*) FROM auction_lots WHERE currency <> 'RMB'", 0),
        ("prices_on_non_sold", "SELECT COUNT(*) FROM auction_lots WHERE sale_status <> '成交' AND sold_price IS NOT NULL", 0),
        ("blank_subcategories", "SELECT COUNT(*) FROM auction_lots WHERE trim(subcategory) = ''", 0),
        ("blank_era_or_artist", "SELECT COUNT(*) FROM auction_lots WHERE trim(era_or_artist) = ''", 0),
        ("duplicate_lot_ids", "SELECT COUNT(*) - COUNT(DISTINCT lot_id) FROM auction_lots", 0),
        ("duplicate_event_lots", "SELECT COUNT(*) - COUNT(DISTINCT (event_id, lot_number)) FROM auction_lots", 0),
        ("blank_internal_ids", "SELECT COUNT(*) FROM auction_lots WHERE lot_id='' OR event_id='' OR auction_house_id=''", 0),
        ("artist_status_mismatch", "SELECT COUNT(*) FROM auction_lots WHERE (attribution_status='已解析作者') <> (artist_name IS NOT NULL)", 0),
        ("invalid_attribution_status", "SELECT COUNT(*) FROM auction_lots WHERE attribution_status NOT IN ('已解析作者','僅有年代','資料不詳','需要確認')", 0),
    ]
    results = []
    for name, query, expected in checks:
        actual = connection.execute(query).fetchone()[0]
        results.append((name, actual, expected, actual == expected))
    category_rows = connection.execute(
        "SELECT category, COUNT(*) FROM auction_lots GROUP BY category ORDER BY category"
    ).fetchall()
    year_rows = connection.execute(
        "SELECT year(auction_date), COUNT(*) FROM auction_lots GROUP BY 1 ORDER BY 1"
    ).fetchall()
    attribution_rows = connection.execute(
        """
        SELECT attribution_status,
               COUNT(*) AS row_count,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM auction_lots), 4) AS percentage
        FROM auction_lots
        GROUP BY attribution_status
        ORDER BY row_count DESC
        """
    ).fetchall()
    connection.close()
    if not all(result[3] for result in results):
        raise AssertionError(f"Validation failed: {results}")
    with (EXPORT_DIR / "validation_summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["check", "actual", "expected", "passed"])
        writer.writerows(results)
    with (EXPORT_DIR / "category_summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["category", "row_count"])
        writer.writerows(category_rows)
    with (EXPORT_DIR / "year_summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["auction_year", "row_count"])
        writer.writerows(year_rows)
    with (EXPORT_DIR / "attribution_status_summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["attribution_status", "row_count", "percentage"])
        writer.writerows(attribution_rows)


def main() -> None:
    rows = generate_rows()
    write_database(rows)
    write_exports(rows)
    validate_and_export()
    print(f"Created {DB_PATH}")
    print(f"Rows: {len(rows):,}")


if __name__ == "__main__":
    main()
