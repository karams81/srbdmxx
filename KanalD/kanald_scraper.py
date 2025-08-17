#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Kanal D Tek Dizi Scraper (yalnızca M3U üretir)
- Sadece aşağıda belirtilen tek bir dizi linkini tarar.
- Ciktilar:
  - <dizi-adi>.m3u
  - programlar/<dizi-adi>.m3u

Kullanım:
  python kanald_scraper.py
"""

import os
import sys
import time
import logging
import json
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from requests.adapters import HTTPAdapter, Retry
from slugify import slugify

# ============================
# !!! DÜZENLEME: Sadece bu link taranacak
# ============================
SINGLE_SERIES_URL = "https://www.kanald.com.tr/esref-ruya"

# ============================
# ÇIKTI KONUMU
# ============================
BASE_DIR = Path(__file__).resolve().parent
ALL_M3U_DIR = str(BASE_DIR)
SERIES_M3U_DIR = str(BASE_DIR / "programlar")

# ============================
# M3U YARDIMCILARI (Değişiklik Gerekmiyor)
# ============================

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def _atomic_write(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)

def _safe_series_filename(name: str) -> str:
    return slugify((name or "dizi").lower()) + ".m3u"

def create_single_series_m3u(folder_path: str, series_data: Dict[str, Any]) -> None:
    """Tek bir dizinin tüm bölümlerini bir M3U dosyasında toplar."""
    if not series_data or not series_data.get("episodes"):
        return
    
    _ensure_dir(folder_path)
    series_name = (series_data.get("name") or "Bilinmeyen Dizi").strip()
    series_logo = (series_data.get("img") or "").strip()
    file_name = _safe_series_filename(series_name)
    master_path = os.path.join(folder_path, file_name)

    lines: List[str] = ["#EXTM3U"]
    for ep in series_data["episodes"]:
        stream = ep.get("stream_url")
        if not stream: continue
        ep_name = ep.get("name") or "Bölüm"
        logo_for_line = series_logo or ep.get("img") or ""
        group = series_name.replace('"', "'")
        lines.append(f'#EXTINF:-1 tvg-logo="{logo_for_line}" group-title="{group}",{ep_name}')
        lines.append(stream)
    
    _atomic_write(master_path, "\n".join(lines) + "\n")

# ============================
# KANAL D SCRAPER (TEK DİZİ ODAKLI)
# ============================

BASE_URL = "https://www.kanald.com.tr/"
VOD_API_URL = "https://www.kanald.com.tr/actions/media"

REQUEST_TIMEOUT = 20
REQUEST_PAUSE = 0.2
BACKOFF_FACTOR = 0.5
MAX_RETRIES = 5

DEFAULT_HEADERS = {
    "Referer": BASE_URL,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("kanald-single-series-scraper")

SESSION = requests.Session()
retries = Retry(total=MAX_RETRIES, backoff_factor=BACKOFF_FACTOR, status_forcelist=(500, 502, 503, 504))
SESSION.mount("https://", HTTPAdapter(max_retries=retries))
SESSION.headers.update(DEFAULT_HEADERS)

def get_soup(url: str) -> Optional[BeautifulSoup]:
    time.sleep(REQUEST_PAUSE)
    try:
        r = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.content, "html.parser")
    except requests.exceptions.RequestException as e:
        log.warning("GET %s hatası: %s", url, e)
        return None

def get_series_info(series_url: str) -> Optional[Dict[str, str]]:
    """Verilen dizi URL'sinden temel bilgileri (isim, poster) alır."""
    log.info("Dizi bilgileri alınıyor: %s", series_url)
    soup = get_soup(series_url)
    if not soup:
        return None
    
    name_tag = soup.select_one("h1.title")
    name = name_tag.get_text(strip=True) if name_tag else "İsimsiz Dizi"
    
    img_tag = soup.select_one("div.poster img.desktop-poster")
    img = img_tag.get("data-src") or img_tag.get("src") if img_tag else ""

    return {"name": name, "url": series_url, "img": urljoin(BASE_URL, img)}

def get_all_episodes_for_series(series_url: str) -> List[Dict[str, str]]:
    """Bir dizinin tüm bölümlerini ve video ID'lerini çeker."""
    all_episodes: List[Dict[str, str]] = []
    episodes_url = urljoin(series_url.rstrip('/') + '/', "bolumler")
    
    page = 1
    while True:
        paginated_url = f"{episodes_url}?p={page}"
        soup = get_soup(paginated_url)
        if not soup: break

        episode_items = soup.select("div.episode-item a")
        if not episode_items: break
        
        for item in episode_items:
            media_id = item.get("data-media-id")
            if not media_id: continue
            title_tag = item.select_one(".title")
            title = title_tag.get_text(strip=True) if title_tag else "Bölüm"
            img_tag = item.select_one("img.desktop-poster")
            img = img_tag.get("data-src") or img_tag.get("src") if img_tag else ""
            all_episodes.append({"name": title, "media_id": media_id, "img": urljoin(BASE_URL, img)})
        
        page += 1
        
    return all_episodes

def get_stream_url_from_media_id(media_id: str) -> Optional[str]:
    time.sleep(REQUEST_PAUSE)
    try:
        payload = {"id": media_id}
        r = SESSION.post(VOD_API_URL, data=payload, timeout=REQUEST_TIMEOUT, headers={"X-Requested-With": "XMLHttpRequest"})
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "success" and "media" in data:
            for file in data["media"].get("files", []):
                if file.get("type") == "application/x-mpegURL":
                    return file.get("url")
        return None
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        log.error("Media ID %s için stream URL alınırken hata: %s", media_id, e)
        return None

def run() -> None:
    """Sadece belirtilen tek dizi için M3U oluşturma işlemini yürütür."""
    series_info = get_series_info(SINGLE_SERIES_URL)
    if not series_info:
        log.error("Dizi bilgileri alınamadı. İşlem durduruluyor.")
        return

    log.info("İşleniyor: %s", series_info.get("name", ""))
    episodes = get_all_episodes_for_series(series_info["url"])
    if not episodes:
        log.warning("%s için hiç bölüm bulunamadı.", series_info.get("name"))
        return

    series_data = dict(series_info)
    series_data["episodes"] = []

    for ep in tqdm(episodes, desc=f"Bölümler ({series_info['name']})"):
        stream_url = get_stream_url_from_media_id(ep["media_id"])
        if stream_url:
            temp_episode = dict(ep)
            temp_episode["stream_url"] = stream_url
            series_data["episodes"].append(temp_episode)
    
    if not series_data["episodes"]:
        log.warning("Hiçbir bölüm için stream URL'si alınamadı.")
        return

    # M3U dosyalarını oluştur
    try:
        # Hem ana klasöre hem de /programlar klasörüne aynı M3U'yu yaz
        create_single_series_m3u(ALL_M3U_DIR, series_data)
        create_single_series_m3u(SERIES_M3U_DIR, series_data)
        log.info("'%s' için M3U dosyaları başarıyla oluşturuldu.", series_data["name"])
    except Exception as e:
        log.error("M3U dosyaları oluşturulurken hata oluştu: %s", e)

def main():
    run()

if __name__ == "__main__":
    main()