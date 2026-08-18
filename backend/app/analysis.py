from __future__ import annotations

import re
from dataclasses import dataclass


CATEGORY_ALIASES: dict[str, str] = {
    "陶瓷": "陶瓷器",
    "陶瓷器": "陶瓷器",
    "瓷器": "陶瓷器",
    "瓷": "陶瓷器",
    "銅器": "銅器",
    "青銅器": "銅器",
    "銅": "銅器",
    "玉器": "玉器",
    "玉": "玉器",
    "繪畫": "繪畫",
    "畫": "繪畫",
    "繪畫類": "繪畫",
    "法書": "法書",
    "書法": "法書",
    "書": "法書",
}


@dataclass(frozen=True)
class QueryIntent:
    key: str
    title: str
    chart_type: str | None = None
    chart_y: str | None = None
    chart_x: str | None = None
    category: str | None = None
    year_grouped: bool = False


def find_category(message: str) -> str | None:
    for alias, category in sorted(CATEGORY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in message:
            return category
    return None


def find_year(message: str) -> int | None:
    match = re.search(r"\b(20(?:20|21|22|23|24|25))\b", message)
    return int(match.group(1)) if match else None


def classify(message: str) -> QueryIntent:
    lowered = message.lower()
    category = find_category(message)
    year_grouped = any(token in lowered for token in ("每年", "年度", "年趨勢", "按年", "逐年"))
    if any(token in lowered for token in ("成交率", "成交比例", "成交百分比")):
        if year_grouped:
            return QueryIntent("annual_sale_rate", "年度成交率趨勢", "line", "sale_rate", "year", category, True)
        return QueryIntent("sale_rate", "各類別成交率", "bar", "sale_rate", "category", category)
    if any(token in lowered for token in ("成交總額", "總成交額", "成交金額", "總成交價")):
        if year_grouped:
            return QueryIntent("annual_sales", "年度成交總額", "line", "total_sold_price", "year", category, True)
        return QueryIntent("sales", "各類別成交總額", "bar", "total_sold_price", "category", category)
    if any(token in lowered for token in ("拍賣公司排名", "哪家拍賣公司", "拍賣公司比較", "公司排名")):
        return QueryIntent("house_ranking", "拍賣公司成交表現", "bar", "sale_rate", "auction_house", category)
    if any(token in lowered for token in ("狀態", "流拍率", "撤拍率", "成交、流拍", "成交流拍")):
        return QueryIntent("status", "成交狀態分布", "bar", "row_count", "sale_status", category)
    if any(token in lowered for token in ("作者排名", "藝術家排名", "哪些作者", "作者統計", "藝術家")):
        return QueryIntent("artist_ranking", "作者成交表現", "bar", "sale_rate", "artist_name", category)
    if any(token in lowered for token in ("估價", "預估價", "估價命中")):
        return QueryIntent("estimate", "估價與成交價比較", "bar", "average_sold_price", "category", category)
    if any(token in lowered for token in ("多少筆", "幾筆", "筆數", "資料量", "幾件")):
        return QueryIntent("counts", "各類別拍品筆數", "bar", "row_count", "category", category)
    if category and any(token in lowered for token in ("明細", "列出", "拍品", "作品", "圖片")):
        return QueryIntent("lot_detail", f"{category}代表性拍品", None, None, None, category)
    return QueryIntent("catalog", "資料集摘要")


def build_sql(intent: QueryIntent, message: str) -> str:
    """Build only known, static query shapes; user text never enters SQL directly."""
    year = find_year(message)
    category_filter = f" AND category = '{intent.category}'" if intent.category else ""
    year_filter = f" AND EXTRACT(YEAR FROM auction_date) = {year}" if year else ""
    if intent.key == "sale_rate":
        return f"""
            SELECT category,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE sale_status='成交') / COUNT(*), 2) AS sale_rate,
                   COUNT(*) AS sample_size
            FROM auction_lots
            WHERE 1=1{category_filter}{year_filter}
            GROUP BY category
            ORDER BY sale_rate DESC, category
        """
    if intent.key == "annual_sale_rate":
        return f"""
            SELECT EXTRACT(YEAR FROM auction_date)::INTEGER AS year,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE sale_status='成交') / COUNT(*), 2) AS sale_rate,
                   COUNT(*) AS sample_size
            FROM auction_lots
            WHERE 1=1{category_filter}{year_filter}
            GROUP BY year
            ORDER BY year
        """
    if intent.key == "sales":
        return f"""
            SELECT category,
                   SUM(sold_price) AS total_sold_price,
                   COUNT(*) FILTER (WHERE sale_status='成交') AS sold_sample_size
            FROM auction_lots
            WHERE sale_status='成交' AND sold_price IS NOT NULL{category_filter}{year_filter}
            GROUP BY category
            ORDER BY total_sold_price DESC, category
        """
    if intent.key == "annual_sales":
        return f"""
            SELECT EXTRACT(YEAR FROM auction_date)::INTEGER AS year,
                   SUM(sold_price) AS total_sold_price,
                   COUNT(*) FILTER (WHERE sale_status='成交') AS sold_sample_size
            FROM auction_lots
            WHERE sale_status='成交' AND sold_price IS NOT NULL{category_filter}{year_filter}
            GROUP BY year
            ORDER BY year
        """
    if intent.key == "house_ranking":
        return f"""
            SELECT auction_house,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE sale_status='成交') / COUNT(*), 2) AS sale_rate,
                   SUM(CASE WHEN sale_status='成交' THEN COALESCE(sold_price, 0) ELSE 0 END) AS total_sold_price,
                   COUNT(*) AS sample_size
            FROM auction_lots
            WHERE 1=1{category_filter}{year_filter}
            GROUP BY auction_house
            HAVING COUNT(*) >= 20
            ORDER BY sale_rate DESC, total_sold_price DESC, auction_house
        """
    if intent.key == "status":
        return f"""
            SELECT sale_status, COUNT(*) AS row_count,
                   ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
            FROM auction_lots
            WHERE 1=1{category_filter}{year_filter}
            GROUP BY sale_status
            ORDER BY row_count DESC, sale_status
        """
    if intent.key == "artist_ranking":
        return f"""
            SELECT artist_name,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE sale_status='成交') / COUNT(*), 2) AS sale_rate,
                   COUNT(*) AS sample_size,
                   SUM(CASE WHEN sale_status='成交' THEN COALESCE(sold_price, 0) ELSE 0 END) AS total_sold_price
            FROM auction_lots
            WHERE artist_name IS NOT NULL AND artist_name <> ''{category_filter}{year_filter}
            GROUP BY artist_name
            HAVING COUNT(*) >= 10
            ORDER BY sale_rate DESC, sample_size DESC, artist_name
        """
    if intent.key == "estimate":
        return f"""
            SELECT category,
                   ROUND(AVG(sold_price), 0) AS average_sold_price,
                   ROUND(AVG((estimate_low + estimate_high) / 2.0), 0) AS average_estimate,
                   COUNT(*) FILTER (WHERE sale_status='成交') AS sold_sample_size
            FROM auction_lots
            WHERE sale_status='成交' AND sold_price IS NOT NULL{category_filter}{year_filter}
            GROUP BY category
            ORDER BY average_sold_price DESC, category
        """
    if intent.key == "counts":
        return f"""
            SELECT category, COUNT(*) AS row_count
            FROM auction_lots
            WHERE 1=1{category_filter}{year_filter}
            GROUP BY category
            ORDER BY category
        """
    if intent.key == "lot_detail":
        return f"""
            SELECT lot_id, category, subcategory, title_zh, era_or_artist, auction_house,
                   auction_event, auction_date, auction_location, lot_number, size_text,
                   estimate_low, estimate_high, sold_price, currency, sale_status, image_url
            FROM auction_lots
            WHERE category = '{intent.category}'{year_filter}
            ORDER BY auction_date DESC, lot_number
            LIMIT 20
        """
    if year:
        return f"""
            SELECT category, COUNT(*) AS row_count,
                   COUNT(*) FILTER (WHERE sale_status='成交') AS sold_count
            FROM auction_lots
            WHERE EXTRACT(YEAR FROM auction_date) = {year}
            GROUP BY category
            ORDER BY category
        """
    return """
        SELECT 'auction_lots' AS table_name, COUNT(*) AS row_count FROM auction_lots
        UNION ALL SELECT 'auction_events', COUNT(*) FROM auction_events
        UNION ALL SELECT 'auction_houses', COUNT(*) FROM auction_houses
        UNION ALL SELECT 'exchange_rates', COUNT(*) FROM exchange_rates
        UNION ALL SELECT 'name_aliases', COUNT(*) FROM name_aliases
    """
