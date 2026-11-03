"""NSE pre-open universe selection from the supplied cash/F&O scripts."""
import csv
import io
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .fno_symbols import FNO_SYMBOLS

MAX_CSV_BYTES = 2_000_000


class PreopenSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    universe: Literal["cash", "fno"] = "cash"
    direction: Literal["gainers", "losers", "both"] = "gainers"
    min_turnover: float = Field(default=0, ge=0, allow_inf_nan=False)
    max_turnover: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    min_change: float = Field(default=0, allow_inf_nan=False)
    max_change: float | None = Field(default=None, allow_inf_nan=False)
    top_n: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def check_ranges(self):
        if self.max_turnover is not None and self.max_turnover < self.min_turnover:
            raise ValueError("Maximum turnover must be at least minimum turnover")
        if self.max_change is not None and self.max_change < self.min_change:
            raise ValueError("Maximum change must be at least minimum change")
        if self.direction == "gainers" and self.min_change < 0:
            raise ValueError("Gainers require a minimum change of zero or greater")
        if self.direction == "losers" and (self.max_change is None or self.max_change > 0):
            raise ValueError("Losers require a maximum change of zero or less")
        if self.direction == "both" and self.max_change is None:
            raise ValueError("Enter a maximum change for Both directions")
        return self


class PreopenRequest(BaseModel):
    csv_text: str = Field(min_length=1, max_length=MAX_CSV_BYTES)
    filename: str = Field(default="NSE pre-open.csv", max_length=255)
    settings: PreopenSettings = Field(default_factory=PreopenSettings)


def numeric(value: str | None) -> float | None:
    text = (value or "").strip().replace(",", "").replace("₹", "").replace("%", "")
    text = re.sub(r"\s*(crores?|cr)\s*$", "", text, flags=re.I)
    try:
        result = float(text)
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def filter_csv(payload: PreopenRequest) -> dict:
    if len(payload.csv_text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("CSV must be no larger than 2 MB")
    settings = payload.settings
    reader = csv.reader(io.StringIO(payload.csv_text.lstrip("\ufeff")), strict=True)
    try:
        headers = [" ".join(col.upper().split()) for col in next(reader)]
        if len(set(headers)) != len(headers):
            raise ValueError("CSV has duplicate column names")
        def column(names):
            return next((headers.index(name) for name in names if name in headers), None)
        symbol_col = column(["SYMBOL", "STOCK", "STOCK SYMBOL", "SYMBOL NAME"])
        # CHANGE is a rupee change in NSE's raw export, never a percentage.
        change_col = column(["%CHANGE", "%CHNG", "% CHANGE", "CHANGE %", "CHANGE%"])
        turnover_col = next((i for i, col in enumerate(headers) if "VALUE" in col and "CRORE" in col), None)
        if turnover_col is None:
            turnover_col = column(["TURNOVER ₹ CR", "TURNOVER CR", "VALUE (₹ CR)", "TOTAL VALUE (₹ CR)", "TURNOVER", "VALUE", "TOTAL VALUE"])
        turnover_unit = "crore"
        # NSE's detailed export uses an unlabelled VALUE column in rupees.
        # Its other export explicitly labels VALUE in crore. Never infer units
        # from the size of a row's value: low-turnover stocks would be misread.
        if turnover_col is not None and headers[turnover_col] in {"VALUE", "TOTAL VALUE", "TURNOVER"}:
            if column(["FINAL VOLUME"]) is not None and column(["FINAL PRICE"]) is not None:
                turnover_unit = "rupees"
        if turnover_col is None:
            turnover_col = column(["VALUE (₹)", "VALUE (RS)", "VALUE (INR)", "VALUE (RUPEES)",
                                   "TURNOVER (₹)", "TURNOVER (RS)", "TURNOVER (INR)"])
            if turnover_col is not None:
                turnover_unit = "rupees"
        if symbol_col is None or change_col is None or turnover_col is None:
            raise ValueError("CSV needs Symbol, percentage change (%CHANGE) and turnover/value in crore columns")
        price_cols = [i for name in ["FINAL PRICE", "IEP", "INDICATIVE EQUILIBRIUM PRICE", "INDICATIVE EQUILIBRIUM PRICE (₹)", "PRICE", "LTP"]
                      if (i := column([name])) is not None]
        total = invalid = duplicates = 0
        rows, seen = [], set()
        for row in reader:
            if not row or not any(cell.strip() for cell in row):
                continue
            total += 1
            if total > 20_000:
                raise ValueError("CSV has more than 20,000 rows")
            if len(row) != len(headers):
                invalid += 1
                continue
            symbol = re.sub(r"\s+", "", re.sub(r"^NSE\s*:\s*", "", row[symbol_col].strip().upper()))
            change, turnover = numeric(row[change_col]), numeric(row[turnover_col])
            if turnover is not None and turnover_unit == "rupees":
                turnover /= 10_000_000
            if (not re.fullmatch(r"[A-Z0-9][A-Z0-9&.\-]*", symbol) or symbol in {"TOTAL", "NAN", "NONE"}
                    or change is None or turnover is None or turnover < 0):
                invalid += 1
                continue
            if symbol in seen:
                duplicates += 1
                continue
            seen.add(symbol)
            price = next((p for i in price_cols if (p := numeric(row[i])) is not None and p > 0), None)
            rows.append({"symbol": symbol, "price": price, "change_percent": change,
                         "turnover_crore": turnover, "is_fno": symbol in FNO_SYMBOLS})
    except StopIteration:
        raise ValueError("CSV is empty") from None
    except csv.Error as exc:
        raise ValueError(f"Invalid CSV: {exc}") from exc
    numeric_matches = [row for row in rows
        if row["turnover_crore"] >= settings.min_turnover
        and (settings.max_turnover is None or row["turnover_crore"] <= settings.max_turnover)
        and row["change_percent"] >= settings.min_change
        and (settings.max_change is None or row["change_percent"] <= settings.max_change)
        and (settings.direction != "gainers" or row["change_percent"] >= 0)
        and (settings.direction != "losers" or row["change_percent"] <= 0)]
    selected = [row for row in numeric_matches if row["is_fno"] == (settings.universe == "fno")]
    selected.sort(key=lambda row: row["turnover_crore"], reverse=True)
    matched = len(selected)
    if settings.top_n is not None:
        selected = selected[:settings.top_n]
    return {"filename": payload.filename, "settings": settings.model_dump(), "total_rows": total,
            "turnover_source_column": headers[turnover_col], "turnover_source_unit": turnover_unit,
            "valid_rows": len(rows), "invalid_rows": invalid, "duplicate_rows": duplicates,
            "numeric_matches": len(numeric_matches), "matched_count": matched,
            "selected_count": len(selected), "fno_list_count": len(FNO_SYMBOLS), "rows": selected,
            "symbols": [row["symbol"] for row in selected]}
