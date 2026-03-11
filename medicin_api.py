import math
import re
import time
from typing import Any

import requests

BASE = "http://api.medicinpriser.dk/v1"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "BIBAWO-Overblik/1.0",
}


def norm_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = s.replace(".", " ")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


NAME_ALIASES = {
    "clonazepam": ["klonazepam", "rivotril", "n03ae01"],
}


def expand_name_aliases(name_query: str) -> list[str]:
    base = norm_text(name_query)
    aliases = NAME_ALIASES.get(base, [])
    out = [base] + [norm_text(x) for x in aliases if x]
    seen = set()
    uniq = []
    for item in out:
        if item and item not in seen:
            uniq.append(item)
            seen.add(item)
    return uniq



def normalize_form(s: str) -> str:
    t = norm_text(s)
    if "dråb" in t or "draab" in t:
        return "dråber"
    if "resor" in t or "smelte" in t or "smeltetablet" in t:
        return "tablet"
    if "bruse" in t and "tablet" in t:
        return "brusetablet"
    if "tablet" in t:
        return "tablet"
    if "kaps" in t:
        return "kapsel"
    if "mikstur" in t:
        return "mikstur"
    if "opløs" in t or "oplos" in t:
        return "opløsning"
    if "suspens" in t:
        return "suspension"
    return t



def norm_pack(s: str) -> str:
    s = norm_text(s)
    s = s.replace("stk.", "stk")
    s = s.replace(" x 1", "")
    s = re.sub(r"\bblist\w*\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s



def ensure_mg(s: str) -> str:
    t = norm_text(s)
    if "/ml" in t:
        return t
    if re.fullmatch(r"\d+(?:[.,]\d+)?", t):
        return f"{t} mg"
    return t



def _coerce_price(val: Any) -> float:
    if val is None or val == "":
        return math.nan
    s = str(val).strip().replace(" ", "").replace(",", ".").lower()
    if "udgået" in s or "udgaet" in s:
        return math.nan
    try:
        x = float(s)
        return x if x >= 0 else math.nan
    except Exception:
        return math.nan



def _get_json(url: str, params: dict | None = None, retries: int = 2, backoff: float = 0.6):
    last_err = None
    for i in range(retries + 1):
        try:
            r = requests.get(url, params=params or {}, headers=HEADERS, timeout=25)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if i < retries:
                time.sleep(backoff * (i + 1))
            else:
                raise last_err



def get_field(d: dict, *candidates):
    if not isinstance(d, dict):
        return None
    for k in candidates:
        if k in d:
            return d[k]
    lower = {k.lower(): v for k, v in d.items()}
    for k in candidates:
        if k.lower() in lower:
            return lower[k.lower()]
    return None



def search_packages(active_name: str):
    results = []
    for name in expand_name_aliases(active_name):
        url = f"{BASE}/produkter/virksomtstof/{requests.utils.quote(name)}"
        try:
            data = _get_json(url, params={"format": "json"})
        except Exception:
            continue

        if isinstance(data, list):
            results.extend(data)
        elif isinstance(data, dict):
            results.extend(data.get("Produkter") or data.get("produkter") or [])
    return results



def get_details(vnr: str):
    url = f"{BASE}/produkter/detaljer/{vnr}"
    data = _get_json(url, params={"format": "json"})
    if isinstance(data, dict) and len(data) == 1 and isinstance(next(iter(data.values())), dict):
        data = next(iter(data.values()))
    return data if isinstance(data, dict) else {}



def extract_stk_qty(s: str):
    m = re.search(r"(\d+)\s*stk\b", s or "")
    return int(m.group(1)) if m else None



def extract_ml_qty(s: str):
    if not s:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*ml\b", str(s), flags=re.I)
    return float(m.group(1).replace(",", ".")) if m else None



def extract_g_qty(s: str):
    if not s:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(g|gram)\b", str(s).lower(), flags=re.I)
    return float(m.group(1).replace(",", ".")) if m else None



def extract_mg_strength(s: str):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*mg\b", s or "")
    if not m:
        return None
    return float(m.group(1).replace(",", "."))



def extract_mg_per_ml(s: str):
    if not s:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*mg\s*/\s*ml\b", str(s), flags=re.I)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))



def strengths_compatible(target: str, actual: str) -> bool:
    t_mgml = extract_mg_per_ml(target)
    a_mgml = extract_mg_per_ml(actual)
    if t_mgml is not None and a_mgml is not None:
        return abs(t_mgml - a_mgml) < 1e-6

    t_mg = extract_mg_strength(target)
    a_mg = extract_mg_strength(actual)
    if t_mg is not None and a_mg is not None:
        return abs(t_mg - a_mg) < 1e-6

    if "%" in (target or "") or "%" in (actual or ""):
        t = (target or "").replace(" ", "")
        a = (actual or "").replace(" ", "")
        return t in a or a in t

    target = norm_text(target)
    actual = norm_text(actual)
    return target in actual or actual in target



def match_row(row: dict, target_form: str, target_strength: str, target_pack: str) -> bool:
    form_raw = get_field(row, "Doseringsform", "Form", "Lægemiddelform")
    strength_raw = get_field(row, "Styrke")
    pack_raw = get_field(row, "Pakningsstørrelse", "Pakning")

    form_norm = normalize_form(form_raw)
    form_ok = (
        form_norm == target_form
        or target_form in form_norm
        or form_norm in target_form
    )
    strength_ok = strengths_compatible(target_strength, norm_text(strength_raw))

    pack_norm = norm_pack(pack_raw)
    tp_stk, rp_stk = extract_stk_qty(target_pack), extract_stk_qty(pack_norm)
    tp_ml, rp_ml = extract_ml_qty(target_pack), extract_ml_qty(pack_norm)
    tp_g, rp_g = extract_g_qty(target_pack), extract_g_qty(pack_norm)

    if tp_stk is not None and rp_stk is not None:
        pack_ok = tp_stk == rp_stk
    elif tp_ml is not None and rp_ml is not None:
        pack_ok = abs(tp_ml - rp_ml) < 1e-6
    elif tp_g is not None and rp_g is not None:
        pack_ok = abs(tp_g - rp_g) < 1e-6
    else:
        pack_ok = (
            target_pack == pack_norm
            or target_pack in pack_norm
            or pack_norm in target_pack
        )

    return form_ok and strength_ok and pack_ok



def find_offers_fuzzy(active_name: str, dosageform: str, strength: str, pack: str):
    target_form = normalize_form(dosageform)
    target_strength = ensure_mg(strength)
    target_pack = norm_pack(pack)

    hits = search_packages(active_name)
    packages = []
    seen = set()

    for row in hits:
        if not isinstance(row, dict):
            continue
        if not match_row(row, target_form, target_strength, target_pack):
            continue

        vnr = str(get_field(row, "Varenummer", "Vnr", "VNR") or "").strip()
        if vnr.isdigit() and len(vnr) < 6:
            vnr = vnr.zfill(6)
        if not vnr or vnr in seen:
            continue
        seen.add(vnr)

        try:
            details = get_details(vnr)
        except Exception:
            continue

        firma = get_field(details, "Virksomhed", "Virksomhedsnavn", "Indehaver", "Firma", "Producent")
        aip = get_field(details, "AIP", "ApoteketsIndkøbspris", "ApoteketsIndkoebspris", "Indkøbspris", "Indkoebspris")
        packages.append({
            "varenummer": vnr,
            "firma": firma,
            "AIP": aip,
        })

    firms = {norm_text(p["firma"]) for p in packages if p.get("firma") and norm_text(p["firma"]) }
    return {
        "count_firms": len(firms),
        "packages": packages,
    }



def get_aip_and_competitors(active_name: str, dosageform: str, strength: str, pack: str):
    result = find_offers_fuzzy(active_name, dosageform, strength, pack)

    prices = []
    valid_firms = set()
    for p in result["packages"]:
        aip = _coerce_price(p.get("AIP"))
        if not math.isnan(aip):
            prices.append(aip)

        firma = p.get("firma")
        if firma:
            valid_firms.add(norm_text(firma))

    return {
        "AIP": min(prices) if prices else math.nan,
        "Konkurrenter": len(valid_firms),
    }
