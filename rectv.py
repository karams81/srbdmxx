import requests
import os
import sys
import re
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any

# --- BÖLÜM 1: AKILLI DOMAIN BULUCU ---

API_KEY = '4F5A9C3D9A86FA54EACEDDD635185/c3c5bd17-e37b-4b94-a944-8a3688a30452'
HEADERS = {
    "User-Agent": "okhttp/4.12.0",
    "Referer": "https://twitter.com/"
}
SOURCE_URL = 'https://raw.githubusercontent.com/kerimmkirac/cs-kerim2/main/RecTV/src/main/kotlin/com/kerimmkirac/RecTV.kt'

def is_url_working(base_url: str) -> bool:
    if not base_url: return False
    test_url = f"{base_url}/api/channel/by/filtres/0/0/0/{API_KEY}/"
    try:
        response = requests.get(test_url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return isinstance(data, list) and len(data) > 0
    except requests.RequestException:
        return False
    return False

def get_url_from_github() -> str:
    try:
        print("Güncel URL GitHub'dan alınıyor...", file=sys.stderr)
        response = requests.get(SOURCE_URL, timeout=15)
        response.raise_for_status()
        content = response.text
        match = re.search(r'override\s+var\s+mainUrl\s*=\s*"([^"]+)"', content)
        if match:
            url = match.group(1).strip('/')
            print(f"GitHub'dan bulunan URL: {url}", file=sys.stderr)
            return url
    except requests.RequestException as e:
        print(f"GitHub'dan URL alınamadı: {e}", file=sys.stderr)
    return ""

def find_working_main_url() -> str:
    print("Çalışan bir ana URL aranıyor...", file=sys.stderr)
    github_url = get_url_from_github()
    if is_url_working(github_url):
        print(f"GitHub URL'si aktif: {github_url}", file=sys.stderr)
        return github_url

    print("GitHub URL'si çalışmıyor. Alternatifler denenecek.", file=sys.stderr)
    for i in range(48, 56):
        potential_url = f"https://m.prectv{i}.sbs"
        print(f"Deneniyor: {potential_url}", file=sys.stderr)
        if is_url_working(potential_url):
            print(f"Aktif URL bulundu: {potential_url}", file=sys.stderr)
            return potential_url
    return ""

# --- BÖLÜM 2: VERİ ÇEKME VE İŞLEME FONKSİYONLARI ---

MAIN_URL = ""

def fetch_url(url: str) -> Optional[Any]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        if response.status_code == 404: return None
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None

def get_all_pages(base_url: str, category_name: str) -> List[Dict]:
    all_items = []
    page = 0
    with tqdm(desc=category_name, unit=" sayfa") as pbar:
        while True:
            url = f"{base_url}{page}/{API_KEY}/"
            data = fetch_url(url)
            if not data or not isinstance(data, list) or len(data) == 0: break
            all_items.extend(data)
            page += 1
            pbar.update(1)
            pbar.set_postfix({'Toplam': len(all_items)})
    return all_items

def get_live_channels() -> Dict[str, List[Dict]]:
    print("\nCanlı yayınlar taranıyor...", file=sys.stderr)
    base_url = f"{MAIN_URL}/api/channel/by/filtres/0/0/"
    all_channels = get_all_pages(base_url, "Canlı Yayınlar")
    categories = {}
    for channel in all_channels:
        if not isinstance(channel, dict): continue
        channel_categories = channel.get('categories', [])
        if not channel_categories: continue
        category_name = channel_categories[0].get('title', 'Diğer')
        if category_name not in categories: categories[category_name] = []
        categories[category_name].append(channel)
    return categories

def get_movies() -> Dict[str, List[Dict]]:
    print("\nFilmler taranıyor...", file=sys.stderr)
    movie_categories = [(0, "Son Filmler"), (14, "Aile"), (1, "Aksiyon"), (13, "Animasyon"), (19, "Belgesel"), (4, "Bilim Kurgu"), (2, "Dram"), (10, "Fantastik"), (3, "Komedi"), (8, "Korku"), (17, "Macera"), (5, "Romantik")]
    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_cat = {executor.submit(get_all_pages, f"{MAIN_URL}/api/movie/by/filtres/{cat_id}/created/", cat_name): cat_name for cat_id, cat_name in movie_categories}
        for future in as_completed(future_to_cat):
            results[future_to_cat[future]] = future.result()
    return results

def get_series() -> Dict[str, List[Dict]]:
    print("\nDizi listeleri taranıyor...", file=sys.stderr)
    series_categories = [(0, "Son Diziler"), (1, "Aksiyon & Macera"), (2, "Dram"), (3, "Komedi"), (4, "Bilim Kurgu & Fantastik"), (5, "Polisiye"), (6, "Romantik"), (7, "Tarih")]
    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_cat = {executor.submit(get_all_pages, f"{MAIN_URL}/api/serie/by/filtres/{cat_id}/created/", cat_name): cat_name for cat_id, cat_name in series_categories}
        for future in as_completed(future_to_cat):
            results[future_to_cat[future]] = future.result()
    return results

def get_episodes_for_serie(serie: Dict) -> List[Dict]:
    if not (serie_id := serie.get('id')): return []
    url = f"{MAIN_URL}/api/season/by/serie/{serie_id}/{API_KEY}/"
    return fetch_url(url) or []

# --- BÖLÜM 3: M3U OLUŞTURMA ---

def generate_m3u():
    global MAIN_URL
    MAIN_URL = find_working_main_url()
    if not MAIN_URL:
        print("HATA: Çalışan hiçbir URL bulunamadı. Script sonlandırılıyor.", file=sys.stderr)
        sys.exit(1)

    with open("rectv_full.m3u", "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")
        live_data = get_live_channels()
        for category, channels in live_data.items():
            for channel in channels:
                if not (sources := channel.get('sources')): continue
                for source in sources:
                    if source.get('type') == 'm3u8' and (url := source.get('url')):
                        name = channel.get('title', 'Bilinmeyen Kanal').split('(')[0].strip()
                        image = channel.get('image', '')
                        f.write(f'#EXTINF:-1 tvg-id="{channel.get("id", "")}" tvg-name="{name}" tvg-logo="{image}" group-title="{category}",{name}\n#EXTVLCOPT:http-user-agent={HEADERS["User-Agent"]}\n#EXTVLCOPT:http-referrer={HEADERS["Referer"]}\n{url}\n\n')
        
        movie_data = get_movies()
        for category, movies in movie_data.items():
            for movie in movies:
                if not (sources := movie.get('sources')) or not (url := sources[0].get('url')): continue
                name = movie.get('title', 'Bilinmeyen Film')
                image = movie.get('image', '')
                f.write(f'#EXTINF:-1 tvg-id="{movie.get("id", "")}" tvg-name="{name}" tvg-logo="{image}" group-title="Filmler;{category}",{name}\n#EXTVLCOPT:http-user-agent={HEADERS["User-Agent"]}\n#EXTVLCOPT:http-referrer={HEADERS["Referer"]}\n{url}\n\n')

        series_data = get_series()
        all_series_list = [item for sublist in series_data.values() for item in sublist]
        print(f"\nToplam {len(all_series_list)} dizi için bölümler taranıyor...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_serie = {executor.submit(get_episodes_for_serie, serie): serie for serie in all_series_list}
            for future in tqdm(as_completed(future_to_serie), total=len(all_series_list), desc="Bölümler İşleniyor"):
                serie, seasons = future_to_serie[future], future.result()
                serie_name, serie_image = serie.get('title', 'Bilinmeyen Dizi'), serie.get('image', '')
                for season in seasons:
                    if not (episodes := season.get('episodes')): continue
                    for episode in episodes:
                        if not (sources := episode.get('sources')) or not (url := sources[0].get('url')): continue
                        s_num = ''.join(filter(str.isdigit, season.get('title', ''))) or '0'
                        e_num = ''.join(filter(str.isdigit, episode.get('title', ''))) or '0'
                        ep_name = f"{serie_name} S{s_num.zfill(2)}E{e_num.zfill(2)}"
                        f.write(f'#EXTINF:-1 tvg-id="{episode.get("id", "")}" tvg-name="{ep_name}" tvg-logo="{serie_image}" group-title="Diziler;{serie_name}",{ep_name}\n#EXTVLCOPT:http-user-agent={HEADERS["User-Agent"]}\n#EXTVLCOPT:http-referrer={HEADERS["Referer"]}\n{url}\n\n')

    print("\nPlaylist oluşturma başarıyla tamamlandı: rectv_full.m3u", file=sys.stderr)

if __name__ == "__main__":
    generate_m3u()