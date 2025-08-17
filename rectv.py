import requests
import os
import sys
import re
import json
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any

# --- BÖLÜM 1: AYARLAR VE AKILLI SUNUCU BULUCU ---

API_KEY = '4F5A9C3D9A86FA54EACEDDD635185/c3c5bd17-e37b-4b94-a944-8a3688a30452'
HEADERS = {"User-Agent": "okhttp/4.12.0", "Referer": "https://twitter.com/"}
PROXY_URL_FORMAT = "https://1.nejyoner19.workers.dev/?url={url}"
OUTPUT_FILENAME = "rectv_full.m3u" # YML dosyası ile uyumlu isim

def find_working_main_url() -> str:
    """
    40-120 arası domainleri tarar ve içinde geçerli .m3u8 linki olan ilk sunucuyu bulur.
    """
    # --- DEĞİŞİKLİK BURADA ---
    # Arama aralığı genişletildi.
    search_range_start = 40
    search_range_end = 120
    print(f"🚀 En iyi sunucu aranıyor ({search_range_start}-{search_range_end})...", file=sys.stderr)
    
    for i in range(search_range_start, search_range_end + 1):
        base_url = f"https://m.prectv{i}.sbs"
        # Test için en garanti yol olan filmlerin ilk sayfasını kullanıyoruz.
        test_url = f"{base_url}/api/movie/by/filtres/0/created/0/{API_KEY}/"
        print(f"[*] Deneniyor: {base_url}", file=sys.stderr)
        try:
            response = requests.get(test_url, headers=HEADERS, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and data:
                    # Sadece listenin dolu olması yetmez, içinde link var mı diye de kontrol edelim.
                    for item in data:
                        if sources := item.get("sources"):
                            for source in sources:
                                if url := source.get("url"):
                                    if isinstance(url, str) and url.endswith(".m3u8"):
                                        print(f"✅ Başarılı! Aktif ve geçerli sunucu bulundu: {base_url}", file=sys.stderr)
                                        return base_url # Çalışan ilk sunucuyu bulduk, döngüden çık.
        except requests.RequestException:
            # Bağlantı hatası olursa sessizce diğerine geç.
            continue
            
    return "" # Eğer tüm aralıkta sunucu bulunamazsa boş döner.

# --- BÖLÜM 2: VERİ ÇEKME VE İŞLEME FONKSİYONLARI (Değişiklik yok) ---

MAIN_URL = ""

def fetch_url(url: str) -> Optional[Any]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        return response.json() if response.status_code == 200 else None
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
    print("\n📺 Canlı yayınlar taranıyor...", file=sys.stderr)
    base_url = f"{MAIN_URL}/api/channel/by/filtres/0/0/"
    all_channels = get_all_pages(base_url, "Canlı Yayınlar")
    categories = {}
    for channel in all_channels:
        if not isinstance(channel, dict): continue
        category_name = (channel.get('categories', [{}])[0].get('title', 'Diğer'))
        if category_name not in categories: categories[category_name] = []
        categories[category_name].append(channel)
    return categories

def get_movies() -> Dict[str, List[Dict]]:
    print("\n🎬 Filmler taranıyor (Tüm Kategoriler)...", file=sys.stderr)
    movie_categories = [(0, "Son Filmler"), (14, "Aile"), (1, "Aksiyon"), (13, "Animasyon"), (19, "Belgesel"), (4, "Bilim Kurgu"), (2, "Dram"), (10, "Fantastik"), (3, "Komedi"), (8, "Korku"), (17, "Macera"), (5, "Romantik")]
    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_cat = {executor.submit(get_all_pages, f"{MAIN_URL}/api/movie/by/filtres/{cat_id}/created/", cat_name): cat_name for cat_id, cat_name in movie_categories}
        for future in as_completed(future_to_cat):
            results[future_to_cat[future]] = future.result()
    return results

def get_series() -> List[Dict]:
    print("\n🎞️ Dizi listeleri taranıyor (Tüm Kategoriler)...", file=sys.stderr)
    series_categories = [(0, "Son Diziler"), (1, "Aksiyon & Macera"), (2, "Dram"), (3, "Komedi"), (4, "Bilim Kurgu & Fantastik"), (5, "Polisiye"), (6, "Romantik"), (7, "Tarih")]
    all_series = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(get_all_pages, f"{MAIN_URL}/api/serie/by/filtres/{cat_id}/created/", cat_name) for cat_id, cat_name in series_categories]
        for future in as_completed(futures):
            all_series.extend(future.result())
    return list({s['id']: s for s in all_series}.values())

def get_episodes_for_serie(serie: Dict) -> List[Dict]:
    if not (serie_id := serie.get('id')): return []
    url = f"{MAIN_URL}/api/season/by/serie/{serie_id}/{API_KEY}/"
    return fetch_url(url) or []

# --- BÖLÜM 3: M3U OLUŞTURMA (Değişiklik yok) ---

def generate_m3u():
    global MAIN_URL
    MAIN_URL = find_working_main_url()
    if not MAIN_URL:
        print("HATA: Çalışan hiçbir sunucu bulunamadı. Script sonlandırılıyor.", file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")
        
        live_data = get_live_channels()
        for category, channels in live_data.items():
            for channel in channels:
                for source in channel.get('sources', []):
                    if source.get('type') == 'm3u8' and (url := source.get('url')):
                        name = channel.get('title', 'Bilinmeyen Kanal').split('(')[0].strip()
                        f.write(f'#EXTINF:-1 tvg-id="{channel.get("id", "")}" tvg-name="{name}" tvg-logo="{channel.get("image", "")}" group-title="{category}",{name}\n')
                        f.write(PROXY_URL_FORMAT.format(url=url) + '\n\n')

        movie_data = get_movies()
        for category, movies in movie_data.items():
            for movie in movies:
                for source in movie.get('sources', []):
                    if url := source.get('url'):
                        if isinstance(url, str) and url.endswith('.m3u8'):
                            name = movie.get('title', 'Bilinmeyen Film')
                            f.write(f'#EXTINF:-1 tvg-id="{movie.get("id", "")}" tvg-name="{name}" tvg-logo="{movie.get("image", "")}" group-title="Filmler;{category}",{name}\n')
                            f.write(PROXY_URL_FORMAT.format(url=url) + '\n\n')
                            break

        all_series_list = get_series()
        print(f"\nToplam {len(all_series_list)} benzersiz dizi için bölümler taranıyor...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_serie = {executor.submit(get_episodes_for_serie, serie): serie for serie in all_series_list}
            for future in tqdm(as_completed(future_to_serie), total=len(all_series_list), desc="Bölümler İşleniyor"):
                serie, seasons = future_to_serie[future], future.result()
                serie_name, serie_image = serie.get('title', 'Bilinmeyen Dizi'), serie.get('image', '')
                for season in seasons:
                    for episode in season.get('episodes', []):
                        for source in episode.get('sources', []):
                            if url := source.get('url'):
                                if isinstance(url, str) and url.endswith('.m3u8'):
                                    s_num = ''.join(filter(str.isdigit, season.get('title', ''))) or '0'
                                    e_num = ''.join(filter(str.isdigit, episode.get('title', ''))) or '0'
                                    ep_name = f"{serie_name} S{s_num.zfill(2)}E{e_num.zfill(2)}"
                                    f.write(f'#EXTINF:-1 tvg-id="{episode.get("id", "")}" tvg-name="{ep_name}" tvg-logo="{serie_image}" group-title="Diziler;{serie_name}",{ep_name}\n')
                                    f.write(PROXY_URL_FORMAT.format(url=url) + '\n\n')
                                    break

    print(f"\n✅ Playlist oluşturma başarıyla tamamlandı: {OUTPUT_FILENAME}", file=sys.stderr)

if __name__ == "__main__":
    generate_m3u()