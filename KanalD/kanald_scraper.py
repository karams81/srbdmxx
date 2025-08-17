#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Kanal D Dizi Scraper (yalnızca M3U üretir)
- Sadece /diziler sayfasını tarar.
- all.m3u       → bu .py dosyasının olduğu klasöre
- programlar/* → her dizi için ayrı M3U (aynı klasör altındaki 'programlar' klasörüne)

Kullanım:
  python kanald_scraper.py
  python kanald_scraper.py 5      (5. diziden başla)
  python kanald_scraper.py 5 10   (5. diziden 10. diziye kadar)

Gereksinimler:
  pip install requests beautifulsoup4 tqdm python-slugify
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
# ÇIKTI KONUMU
# ============================
BASE_DIR = Path(__file__).resolve().parent
ALL_M3U_DIR = str(BASE_DIR)
ALL_M3U_NAME = "KanalD-Diziler" # Dosya adını daha açıklayıcı yaptım
SERIES_M3U_DIR = str(BASE_DIR / "programlar")
SERIES_MASTER = False

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

def create_m3us(channel_folder_path: str,
                data: List[Dict[str, Any]],
                master: bool = False,
                base_url: str = "") -> None:
    _ensure_dir(channel_folder_path)
    # ... (Bu fonksiyonun içeriği öncekiyle aynı, değişiklik yok)
    master_lines: List[str] = ["#EXTM3U"] if master else []
    if base_url and not base_url.endswith(("/", "\\")):
        base_url = base_url + "/"
    for serie in (data or []):
        episodes = serie.get("episodes") or []
        if not episodes: continue
        series_name = (serie.get("name") or "Bilinmeyen Seri").strip()
        series_logo = (serie.get("img") or "").strip()
        plist_name = _safe_series_filename(series_name)
        plist_path = os.path.join(channel_folder_path, plist_name)
        lines: List[str] = ["#EXTM3U"]
        for ep in episodes:
            stream = ep.get("stream_url")
            if not stream: continue
            ep_name = ep.get("name") or "Bölüm"
            logo_for_line = series_logo or ep.get("img") or ""
            group = series_name.replace('"', "'")
            lines.append(f'#EXTINF:-1 tvg-logo="{logo_for_line}" group-title="{group}",{ep_name}')
            lines.append(stream)
        if len(lines) > 1:
            _atomic_write(plist_path, "\n".join(lines) + "\n")
            if master:
                master_lines.append(f'#EXTINF:-1 tvg-logo="{series_logo}", {series_name}')
                master_lines.append(f'{base_url}{plist_name}')
    if master:
        master_path = os.path.join(channel_folder_path, "0.m3u")
        _atomic_write(master_path, "\n".join(master_lines) + "\n")


def create_single_m3u(channel_folder_path: str,
                      data: List[Dict[str, Any]],
                      custom_path: str = "0") -> None:
    _ensure_dir(channel_folder_path)
    # ... (Bu fonksiyonun içeriği öncekiyle aynı, değişiklik yok)
    master_path = os.path.join(channel_folder_path, f"{custom_path}.m3u")
    lines: List[str] = ["#EXTM3U"]
    for serie in (data or []):
        series_name = (serie.get("name") or "Bilinmeyen Seri").strip()
        series_logo = (serie.get("img") or "").strip()
        episodes = serie.get("episodes") or []
        for ep in episodes:
            stream = ep.get("stream_url")
            if not stream: continue
            ep_name = ep.get("name") or "Bölüm"
            logo_for_line = series_logo or ep.get("img") or ""
            group = series_name.replace('"', "'")
            lines.append(f'#EXTINF:-1 tvg-logo="{logo_for_line}" group-title="{group}",{ep_name}')
            lines.append(stream)
    _atomic_write(master_path, "\n".join(lines) + "\n")

# ============================
# KANAL D SCRAPER (SADECE DİZİLER)
# ============================

BASE_URL = "https://www.kanald.com.tr/"
# !!! DEĞİŞİKLİK: Hedefi /programlar yerine /diziler olarak güncelledik
TARGET_URL = urljoin(BASE_URL, "diziler")
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
log = logging.getLogger("kanald-dizi-scraper")

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

def get_all_series() -> List[Dict[str, str]]:
    """Tüm dizilerin listesini çeker (sayfalamayı destekler)."""
    log.info("Tüm diziler listesi alınıyor...")
    all_series: List[Dict[str, str]] = []
    page = 1
    while True:
        paginated_url = f"{TARGET_URL}?p={page}"
        log.info("Sayfa %d taranıyor...", page)
        
        soup = get_soup(paginated_url)
        if not soup:
            log.warning("Diziler sayfası %d alınamadı, döngü sonlandırılıyor.", page)
            break

        series_items = soup.select("div.archive-item a")
        
        if not series_items:
            log.info("Son sayfaya ulaşıldı (sayfa %d).", page)
            break

        for item in series_items:
            url = item.get("href")
            if not url: continue
            
            name_tag = item.select_one("div.title")
            name = name_tag.get_text(strip=True) if name_tag else "İsimsiz Dizi"
            
            img_tag = item.select_one("img.desktop-poster")
            img = img_tag.get("data-src") or img_tag.get("src") if img_tag else ""

            all_series.append({
                "name": name,
                "url": urljoin(BASE_URL, url),
                "img": urljoin(BASE_URL, img)
            })
        
        page += 1
        time.sleep(0.1)

    log.info("Tarama tamamlandı. Toplam %d dizi bulundu.", len(all_series))
    return all_series

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

def run(start: int = 0, end: int = 0) -> Dict[str, Any]:
    output: List[Dict[str, Any]] = []
    series_list = get_all_series()
    if not series_list:
        log.error("Hiç dizi bulunamadı. İşlem durduruluyor.")
        return {"programs": []}

    end_index = len(series_list) if end == 0 else min(end, len(series_list))
    start_index = max(0, start)

    for i in tqdm(range(start_index, end_index), desc="Diziler"):
        series = series_list[i]
        log.info("İşleniyor: %d/%d | %s", i + 1, end_index, series.get("name", ""))
        episodes = get_all_episodes_for_series(series["url"])
        if not episodes:
            log.warning("%s için hiç bölüm bulunamadı.", series.get("name"))
            continue
        temp_series = dict(series)
        temp_series["episodes"] = []
        for ep in tqdm(episodes, desc=f"Bölümler ({series['name']})", leave=False):
            stream_url = get_stream_url_from_media_id(ep["media_id"])
            if stream_url:
                temp_episode = dict(ep)
                temp_episode["stream_url"] = stream_url
                temp_series["episodes"].append(temp_episode)
        if temp_series["episodes"]:
            output.append(temp_series)
    return {"programs": output}

def save_outputs(data: Dict[str, Any]) -> None:
    programs = data.get("programs", [])
    if not programs:
        log.warning("Kaydedilecek veri bulunamadı.")
        return
    try:
        create_single_m3u(ALL_M3U_DIR, programs, ALL_M3U_NAME)
        create_m3us(SERIES_M3U_DIR, programs, master=SERIES_MASTER)
        log.info("Tüm M3U dosyaları başarıyla oluşturuldu.")
    except Exception as e:
        log.error("M3U dosyaları oluşturulurken hata oluştu: %s", e)

def parse_args(argv: List[str]) -> Tuple[int, int]:
    start, end = 0, 0
    if len(argv) >= 2:
        try: start = int(argv[1])
        except Exception: pass
    if len(argv) >= 3:
        try: end = int(argv[2])
        except Exception: pass
    return start, end

def main():
    start, end = parse_args(sys.argv)
    data = run(start=start, end=end)
    save_outputs(data)

if __name__ == "__main__":
    main()