#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Kanal D scraper (yalnızca M3U üretir)
- all.m3u       → bu .py dosyasının olduğu klasöre
- programlar/* → her dizi için ayrı M3U (aynı klasör altındaki 'programlar' klasörüne)

Kullanım:
  python kanald_scraper.py
  python kanald_scraper.py 10      (10. programdan başla)
  python kanald_scraper.py 10 50   (10. programdan 50. programa kadar)

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
# ÇIKTI KONUMU (.py ile aynı klasör)
# ============================
BASE_DIR = Path(__file__).resolve().parent
ALL_M3U_DIR = str(BASE_DIR)
ALL_M3U_NAME = "KanalD"
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
# KANAL D SCRAPER
# ============================

BASE_URL = "https://www.kanald.com.tr/"
PROGRAMS_URL = urljoin(BASE_URL, "programlar")
# Kanal D'nin video bilgilerini ve m3u8 linkini veren API'si
VOD_API_URL = "https://www.kanald.com.tr/actions/media"

REQUEST_TIMEOUT = 20
REQUEST_PAUSE = 0.2
BACKOFF_FACTOR = 0.5
MAX_RETRIES = 5

DEFAULT_HEADERS = {
    "Referer": BASE_URL,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("kanald-scraper")

SESSION = requests.Session()
retries = Retry(total=MAX_RETRIES, backoff_factor=BACKOFF_FACTOR, status_forcelist=(500, 502, 503, 504))
SESSION.mount("https://", HTTPAdapter(max_retries=retries))
SESSION.headers.update(DEFAULT_HEADERS)

def get_soup(url: str) -> Optional[BeautifulSoup]:
    """Verilen URL'den sayfa çeker ve BeautifulSoup objesi döndürür."""
    time.sleep(REQUEST_PAUSE)
    try:
        r = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.content, "html.parser")
    except requests.exceptions.RequestException as e:
        log.warning("GET %s hatası: %s", url, e)
        return None

def get_all_programs() -> List[Dict[str, str]]:
    """Tüm programların listesini çeker."""
    log.info("Tüm programlar listesi alınıyor...")
    all_programs: List[Dict[str, str]] = []
    soup = get_soup(PROGRAMS_URL)
    if not soup:
        log.error("Programlar ana sayfası alınamadı.")
        return all_programs

    program_items = soup.select("div.archive-item a")
    for item in program_items:
        url = item.get("href")
        if not url: continue
        
        name_tag = item.select_one("div.title")
        name = name_tag.get_text(strip=True) if name_tag else "İsimsiz Program"
        
        img_tag = item.select_one("img.desktop-poster")
        img = img_tag.get("data-src") or img_tag.get("src") if img_tag else ""

        all_programs.append({
            "name": name,
            "url": urljoin(BASE_URL, url),
            "img": urljoin(BASE_URL, img)
        })
    log.info("%d program bulundu.", len(all_programs))
    return all_programs

def get_all_episodes_for_program(program_url: str) -> List[Dict[str, str]]:
    """Bir programın tüm bölümlerini ve video ID'lerini çeker."""
    all_episodes: List[Dict[str, str]] = []
    
    # Bölümler genellikle program ana sayfasının sonuna "/bolumler" eklenerek bulunur
    episodes_url = urljoin(program_url + "/", "bolumler")
    
    page = 1
    while True:
        paginated_url = f"{episodes_url}?p={page}"
        soup = get_soup(paginated_url)
        if not soup:
            log.warning("%s için bölüm sayfası %d alınamadı.", program_url, page)
            break

        episode_items = soup.select("div.episode-item a")
        if not episode_items:
            # Eğer hiç bölüm bulunamazsa döngüyü sonlandır
            break
        
        for item in episode_items:
            url = item.get("href")
            if not url: continue

            media_id = item.get("data-media-id")
            if not media_id: continue

            title_tag = item.select_one(".title")
            title = title_tag.get_text(strip=True) if title_tag else "Bölüm"
            
            img_tag = item.select_one("img.desktop-poster")
            img = img_tag.get("data-src") or img_tag.get("src") if img_tag else ""

            all_episodes.append({
                "name": title,
                "media_id": media_id,
                "img": urljoin(BASE_URL, img)
            })
        
        log.info("%s için %d. sayfadan %d bölüm eklendi.", program_url.split('/')[-1], page, len(episode_items))
        page += 1
        
    return all_episodes

def get_stream_url_from_media_id(media_id: str) -> Optional[str]:
    """Media ID kullanarak VOD API'sinden .m3u8 linkini alır."""
    time.sleep(REQUEST_PAUSE)
    try:
        # Kanal D'nin video API'sine media_id ile POST isteği gönderiyoruz
        payload = {"id": media_id}
        r = SESSION.post(VOD_API_URL, data=payload, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        
        # API cevabındaki media objesinden m3u8 linkini alıyoruz
        if data.get("status") == "success" and "media" in data:
            media_files = data["media"].get("files", [])
            for file in media_files:
                if file.get("type") == "application/x-mpegURL":
                    return file.get("url")
        log.warning("Media ID %s için M3U8 linki bulunamadı. API yanıtı: %s", media_id, data)
        return None
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        log.error("Media ID %s için stream URL alınırken hata: %s", media_id, e)
        return None

def run(start: int = 0, end: int = 0) -> Dict[str, Any]:
    output: List[Dict[str, Any]] = []
    programs_list = get_all_programs()
    if not programs_list:
        log.error("Hiç program bulunamadı. İşlem durduruluyor.")
        return {"programs": []}

    end_index = len(programs_list) if end == 0 else min(end, len(programs_list))
    start_index = max(0, start)

    for i in tqdm(range(start_index, end_index), desc="Programlar"):
        program = programs_list[i]
        log.info("İşleniyor: %d/%d | %s", i + 1, end_index, program.get("name", ""))

        episodes = get_all_episodes_for_program(program["url"])
        if not episodes:
            log.warning("%s için hiç bölüm bulunamadı.", program.get("name"))
            continue

        temp_program = dict(program)
        temp_program["episodes"] = []

        for ep in tqdm(episodes, desc=f"Bölümler ({program['name']})", leave=False):
            stream_url = get_stream_url_from_media_id(ep["media_id"])
            if stream_url:
                temp_episode = dict(ep)
                temp_episode["stream_url"] = stream_url
                temp_program["episodes"].append(temp_episode)
            else:
                log.warning("Stream URL alınamadı: %s - %s", program['name'], ep['name'])

        if temp_program["episodes"]:
            output.append(temp_program)

    return {"programs": output}

def save_outputs(data: Dict[str, Any]) -> None:
    """M3U dosyalarını oluşturur."""
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
