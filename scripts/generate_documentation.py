from __future__ import annotations

import csv
from pathlib import Path

import duckdb

from generate_auction_lots import (
    CATEGORIES,
    CURRENCY,
    DB_PATH,
    EXPORT_DIR,
    ROWS_PER_CATEGORY,
    ROWS_PER_YEAR,
    SCHEMA,
    SEED,
    SUBCATEGORY_RULES,
    YEARS,
)


TABLES = (
    "auction_lots",
    "auction_events",
    "auction_houses",
    "exchange_rates",
    "name_aliases",
)

TABLE_DESCRIPTIONS = {
    "auction_lots": "拍賣年鑑式拍品主表；前 16 欄為展示欄位，後 6 欄供內部關聯與分析。",
    "auction_events": "拍賣場次主檔；每個 event_id 代表一個拍賣公司、日期、地區與分類的場次。",
    "auction_houses": "拍賣公司主檔；保存標準公司名稱與主要所在地。",
    "exchange_rates": "2020–2025 每日外幣兌人民幣匯率；非發布日沿用最近可得來源日。",
    "name_aliases": "拍賣公司名稱對應表；將中英文或不同寫法正規化為標準名稱。",
}

FIELD_DESCRIPTIONS = {
    "auction_lots": {name: description for name, _, description in SCHEMA},
    "auction_events": {
        "event_id": "內部使用的拍賣場次唯一識別碼。",
        "auction_house_id": "舉辦場次的拍賣公司識別碼。",
        "auction_event": "拍賣場次名稱。",
        "auction_date": "拍賣日期。",
        "auction_location": "拍賣地區。",
        "category": "本場次對應的拍品大分類。",
        "data_status": "標示場次資料為模擬或真實。",
    },
    "auction_houses": {
        "auction_house_id": "拍賣公司唯一識別碼。",
        "auction_house_name": "拍賣公司的標準中文名稱。",
        "main_city": "拍賣公司主要城市。",
        "country_region": "拍賣公司主要國家或地區。",
    },
    "exchange_rates": {
        "rate_date": "此匯率適用的日期。",
        "source_date": "實際取得匯率的香港金融管理局資料日期。",
        "from_currency": "換算前幣別。",
        "to_currency": "換算後幣別，固定為 RMB。",
        "rate_to_rmb": "一單位原幣可換得的人民幣金額。",
        "source_hkd_per_unit": "來源資料中的一單位原幣兌港幣值。",
        "cny_hkd_per_unit": "來源資料中的一人民幣兌港幣值。",
        "is_carried_forward": "是否因非發布日而沿用最近可得匯率。",
        "source_name": "匯率來源機構。",
        "source_url": "匯率來源網址。",
    },
    "name_aliases": {
        "alias_id": "名稱對應紀錄的唯一識別碼。",
        "entity_type": "別名所屬實體類型。",
        "alias_name": "可能出現在輸入資料或問題中的名稱寫法。",
        "canonical_name": "正規化後的標準名稱。",
        "auction_house_id": "對應的拍賣公司識別碼。",
        "language": "名稱寫法的語言。",
    },
}

KEY_RULES = {
    ("auction_lots", "lot_id"): "UNIQUE；內部全域識別碼",
    ("auction_lots", "event_id"): "複合唯一鍵之一：event_id + lot_number",
    ("auction_lots", "lot_number"): "複合唯一鍵之一：event_id + lot_number",
    ("auction_events", "event_id"): "PRIMARY KEY",
    ("auction_houses", "auction_house_id"): "PRIMARY KEY",
    ("auction_houses", "auction_house_name"): "UNIQUE",
    ("exchange_rates", "rate_date"): "複合主鍵之一：rate_date + from_currency + to_currency",
    ("exchange_rates", "from_currency"): "複合主鍵之一：rate_date + from_currency + to_currency",
    ("exchange_rates", "to_currency"): "複合主鍵之一：rate_date + from_currency + to_currency",
    ("name_aliases", "alias_id"): "PRIMARY KEY",
    ("name_aliases", "entity_type"): "複合唯一鍵之一：entity_type + alias_name",
    ("name_aliases", "alias_name"): "複合唯一鍵之一：entity_type + alias_name",
}

REFERENCES = {
    ("auction_lots", "event_id"): "auction_events.event_id（邏輯外鍵；由驗證檔檢查）",
    ("auction_lots", "auction_house_id"): "auction_houses.auction_house_id（邏輯外鍵；由驗證檔檢查）",
    ("auction_events", "auction_house_id"): "auction_houses.auction_house_id",
    ("name_aliases", "auction_house_id"): "auction_houses.auction_house_id",
}

ALLOWED_VALUES = {
    ("auction_lots", "category"): "陶瓷器｜銅器｜玉器｜繪畫｜法書",
    ("auction_lots", "currency"): "RMB",
    ("auction_lots", "sale_status"): "成交｜流拍｜撤拍",
    ("auction_lots", "attribution_status"): "已解析作者｜僅有年代｜資料不詳｜需要確認",
    ("auction_events", "category"): "陶瓷器｜銅器｜玉器｜繪畫｜法書",
    ("auction_events", "data_status"): "模擬",
    ("exchange_rates", "from_currency"): "USD｜HKD｜GBP｜EUR｜JPY｜TWD",
    ("exchange_rates", "to_currency"): "RMB",
    ("exchange_rates", "is_carried_forward"): "true｜false",
    ("name_aliases", "entity_type"): "auction_house",
    ("name_aliases", "language"): "zh｜en",
}

NULL_RULES = {
    ("auction_lots", "sold_price"): "成交時必填；流拍或撤拍時必須為 NULL。",
    ("auction_lots", "artist_name"): "僅在高可信度解析出作者時填值，否則為 NULL。",
    ("auction_lots", "era_name"): "故宮來源年代缺漏或不詳時為 NULL。",
    ("auction_lots", "size_text"): "故宮來源沒有尺寸時可為空字串。",
}


def write_data_dictionary() -> None:
    connection = duckdb.connect(str(DB_PATH), read_only=True)
    rows: list[dict] = []
    for table_name in TABLES:
        table_info = connection.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        for cid, column_name, data_type, not_null, _default, primary_key in table_info:
            logical_nullable = "是" if (table_name, column_name) in {
                ("auction_lots", "sold_price"),
                ("auction_lots", "artist_name"),
                ("auction_lots", "era_name"),
            } else "否"
            key_rule = KEY_RULES.get((table_name, column_name), "")
            if primary_key and not key_rule:
                key_rule = "PRIMARY KEY"
            rows.append(
                {
                    "table_name": table_name,
                    "table_description": TABLE_DESCRIPTIONS[table_name],
                    "column_order": cid + 1,
                    "column_name": column_name,
                    "data_type": data_type,
                    "nullable_in_database": "否" if not_null else "是",
                    "nullable_by_business_rule": logical_nullable,
                    "key_or_constraint": key_rule,
                    "references": REFERENCES.get((table_name, column_name), ""),
                    "allowed_values": ALLOWED_VALUES.get((table_name, column_name), ""),
                    "null_rule": NULL_RULES.get(
                        (table_name, column_name),
                        "依目前資料規格必填，不應為 NULL。" if logical_nullable == "否" else "可為 NULL。",
                    ),
                    "description": FIELD_DESCRIPTIONS[table_name][column_name],
                }
            )
    connection.close()
    target = EXPORT_DIR / "data_dictionary.csv"
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_generation_rules() -> None:
    lines = [
        "# 資料集與解析規則",
        "",
        "此文件供資料分析代理、評審與後續開發者判讀資料。規則與產生程式使用相同常數輸出。",
        "",
        "## 1. 資料來源與模擬範圍",
        "",
        "- 真實欄位：故宮 Open Data 的中文品名、年代、尺寸、圖片網址，以及由 API 類別決定的大分類。",
        "- 模擬欄位：拍賣公司、場次、日期、地區、Lot 編號、估價、成交價、幣別與成交狀態。",
        "- 本資料不代表故宮藏品的真實拍賣紀錄，回答時必須揭露這一點。",
        f"- 固定亂數種子：`{SEED}`，使資料可重現。",
        f"- 年度：`{min(YEARS)}–{max(YEARS)}`，每年 `{ROWS_PER_YEAR:,}` 筆。",
        f"- 類別：每類 `{ROWS_PER_CATEGORY:,}` 筆，共 `{ROWS_PER_CATEGORY * len(CATEGORIES):,}` 筆。",
        "- 拍賣日期只安排在星期六或星期日。",
        "- 成交狀態固定比例：成交 80%、流拍 17%、撤拍 3%。",
        f"- 幣別固定為 `{CURRENCY}`；流拍與撤拍的 `sold_price` 為 NULL。",
        "",
        "## 2. 唯一值與跨表關聯",
        "",
        "- `lot_number` 只保證在同一場次內唯一，不能單獨當全域鍵。",
        "- 業務唯一鍵為 `event_id + lot_number`。",
        "- `lot_id` 是由 `event_id|lot_number` 計算的穩定全域識別碼，格式為 `LOT-` 加 12 碼 SHA-1 摘要。",
        "- 年鑑式展示可隱藏 `lot_id`、`event_id`、`auction_house_id`、`artist_name`、`era_name`、`attribution_status`。",
        "",
        "## 3. subcategory 細分類規則",
        "",
        "先移除品名空白，再依下列順序比對關鍵字；命中第一條即停止。每個大分類最後一條是未命中時的 fallback。",
        "",
    ]
    for category, rules in SUBCATEGORY_RULES.items():
        lines.extend((f"### {category}", "", "| 優先序 | subcategory | 品名關鍵字 |", "|---:|---|---|"))
        for index, (label, keywords) in enumerate(rules, start=1):
            keyword_text = "、".join(f"`{keyword}`" for keyword in keywords) if keywords else "未命中前述規則時使用"
            lines.append(f"| {index} | {label} | {keyword_text} |")
        lines.append("")
    lines.extend(
        [
            "## 4. 作者與年代解析規則",
            "",
            "- 書籍展示欄仍保留 `era_or_artist`（年代／作者），不改變年鑑表面格式。",
            "- 只有 `繪畫` 與 `法書` 會從中文品名解析作者；其餘類別不猜作者。",
            "- 先移除空白，再尋找『年代／朝代 + 2–4 個中文字姓名 + 創作標記』的高可信度型態。",
            "- 創作標記包括畫、繪、書、詩、題、臨、寫、作、製等；泛稱、器物詞與以畫／書／詩／法／山水／花卉結尾的候選會排除。",
            "- `已解析作者`：成功取得高可信度作者，`artist_name` 有值。",
            "- `僅有年代`：沒有可靠作者，但故宮年代欄有可用值，`era_name` 有值。",
            "- `資料不詳`：作者與可用年代皆沒有，兩欄為 NULL。",
            "- `需要確認`：年代包含『待訂』，不強行歸入確定年代。",
            "- 不使用純 random 作者，避免產生與故宮品名矛盾的歸屬。",
            "",
            "## 5. 價格與場次模擬",
            "",
            "- 每個大分類使用不同價格中位數與離散程度，以對數常態分布產生估價，並限制在合理的大範圍內。",
            "- 最高估價一定大於最低估價；成交品可能低於估價、落在估價內或高於最高估價。",
            "- 每年、每分類、每拍賣公司建立春季與秋季各一場，共 900 場。",
            "- `auction_events.data_status` 固定為『模擬』。",
            "",
            "## 6. 代理回答注意事項",
            "",
            "- 查詢拍品時以 `event_id + lot_number` 或 `lot_id` 定位，不以 `lot_number` 單獨定位。",
            "- 作者分析優先使用 `artist_name`，年代分析使用 `era_name`；不要把 `era_or_artist` 直接當作者。",
            "- 匯率轉換使用拍賣日對應的 `exchange_rates.rate_date`；資料目前成交幣別均為 RMB，換算表供未來擴充與展示。",
            "- 統計成交額只納入 `sale_status='成交'` 且 `sold_price` 非 NULL 的資料。",
        ]
    )
    (EXPORT_DIR / "data_generation_rules.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_data_dictionary()
    write_generation_rules()
    print(f"Created {EXPORT_DIR / 'data_dictionary.csv'}")
    print(f"Created {EXPORT_DIR / 'data_generation_rules.md'}")


if __name__ == "__main__":
    main()
