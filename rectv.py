import requests
import os
import sys
import re
import json
from tqdm import tqdm
from typing import Dict, List, Optional, Any

# --- BÖLÜM 1: AYARLAR VE GÜVENİLİR SUNUCU BULUCU ---

API_KEY = '4F5A9C3D9A86FA54EACEDDD635185/c3c5bd17-e37b-4b94-a944-8a3688a30452'
HEADERS = {"User-Agent": "okhttp/4.12.0", "Referer": "https://twitter.com/"}
OUTPUT_FILENAME = "rectv_full.m3u"
SOURCE_URL = 'https://raw.githubusercontent.com/kerimmkirac/cs-kerim2/main/RecTV/src/main/kotlin/com/kerimmkirac/RecTV.kt'

# Sunucu arama aralığı, gerekirse kolayca değiştirilebilir
SEARCH_RANGE_START = 40
SEARCH_RANGE_END = 150 # Aralığı daha da genişlettik

def is_url_working_and_has_content(base_url: str) -> bool:
    """Bir URL'nin çalışıp çalışmadığını ve içinde veri olup olmadığını test eder."""
    if not base_url: return False
    # Filtre ID'si 0, genellikle "Tümü" veya "Son Eklenenler" anlamına gelir ve en güvenilir test noktasıdır.
    test_url = f"{base_url}/api/movie/by/filtres/0/created/0/{API_KEY}/"
    try:
        # Timeout süresini biraz artırarak zayıf bağlantılarda hata almayı önleyelim.
        response = requests.get(test_url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            # API'den geçerli ve dolu bir liste dönüp dönmediğini kontrol et
            return isinstance(data, list) and len(data) > 0
    except requests.RequestException as e:
        print(f"URL test hatası: {base_url} -> {e}", file=sys.stderr)
        return False
    return False

def get_url_from_github() -> str:
    """GitHub reposundan en güncel URL'yi almayı dener."""
    try:
        print("Öncelikli kaynak (GitHub) kontrol ediliyor...", file=sys.stderr)
        response = requests.get(SOURCE_URL, timeout=15)
        response.raise_for_status()
        content = response.text
        # Regex ile ana URL'yi kodun içinden bul
        match = re.search(r'override\s+var\s+mainUrl\s*=\s*"([^"]+)"', content)
        if match:
            url = match.group(1).strip('/')
            print(f"GitHub'dan bulunan URL: {url}", file=sys.stderr)
            return url
    except requests.RequestException as e:
        print(f"GitHub'dan URL alınamadı: {e}", file=sys.stderr)
    return ""

def find_working_main_url() -> str:
    """Çalışan ilk geçerli ana URL'yi bulur."""
    github_url = get_url_from_github()
    if is_url_working_and_has_content(github_url):
        print(f"✅ Öncelikli kaynak aktif: {github_url}", file=sys.stderr)
        return github_url

    print(f"Öncelikli kaynak çalışmıyor. Geniş aralık ({SEARCH_RANGE_START}-{SEARCH_RANGE_END}) taranacak...", file=sys.stderr)
    # Belirtilen aralıktaki tüm potansiyel sunucuları dene
    for i in range(SEARCH_RANGE_START, SEARCH_RANGE_END + 1):
        base_url = f"https://m.prectv{i}.sbs"
        print(f"[*] Deneniyor: {base_url}", file=sys.stderr)
        if is_url_working_and_has_content(base_url):
            print(f"✅ Aktif sunucu bulundu: {base_url}", file=sys.stderr)
            return base_url
    return ""

# --- BÖLÜM 2: SIRALI (GÜVENİLİR) VERİ ÇEKME ---

MAIN_URL = ""

def fetch_url(url: str) -> Optional[Any]:
    """Verilen URL'den JSON verisi çeker."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        return response.json() if response.status_code == 200 else None
    except requests.RequestException:
        return None

def get_all_pages(base_url: str, category_name: str) -> List[Dict]:
    """Bir kategori için tüm sayfaları sonuna kadar çeker."""
    all_items = []
    page = 0
    # tqdm ile ilerleme çubuğu oluşturarak kullanıcıyı bilgilendir
    with tqdm(desc=category_name, unit=" sayfa") as pbar:
        while True:
            # Sayfa numarasını URL'ye ekleyerek sıradaki sayfayı iste
            url = f"{base_url}{page}/{API_KEY}/"
            data = fetch_url(url)
            # API'den boş veya geçersiz veri gelirse döngüyü sonlandır
            if not data or not isinstance(data, list) or len(data) == 0:
                break
            all_items.extend(data)
            page += 1
            pbar.update(1)
            # İlerleme çubuğunda toplam çekilen içerik sayısını göster
            pbar.set_postfix({'Toplam': len(all_items)})
    return all_items

def get_episodes_for_serie(serie: Dict) -> List[Dict]:
    """Bir diziye ait tüm sezon ve bölümleri çeker."""
    if not (serie_id := serie.get('id')): return []
    url = f"{MAIN_URL}/api/season/by/serie/{serie_id}/{API_KEY}/"
    return fetch_url(url) or []

# --- BÖLÜM 3: M3U OLUŞTURMA (TÜM İÇERİK) ---

def generate_m3u():
    global MAIN_URL
    MAIN_URL = find_working_main_url()
    if not MAIN_URL:
        print("HATA: Çalışan hiçbir sunucu bulunamadı. Script sonlandırılıyor.", file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")
        
        # 1. Canlı Yayınlar
        print("\n📺 Canlı yayınlar taranıyor...", file=sys.stderr)
        live_base_url = f"{MAIN_URL}/api/channel/by/filtres/0/0/"
        all_channels = get_all_pages(live_base_url, "Canlı Yayınlar")
        categories = {}
        for channel in all_channels:
            if not isinstance(channel, dict): continue
            category_name = (channel.get('categories', [{}])[0].get('title', 'Diğer'))
            if category_name not in categories: categories[category_name] = []
            categories[category_name].append(channel)
        
        for category, channels in categories.items():
            for channel in channels:
                for source in channel.get('sources', []):
                    if source.get('type') == 'm3u8' and (url := source.get('url')):
                        name = channel.get('title', 'Bilinmeyen Kanal').split('(')[0].strip()
                        f.write(f'#EXTINF:-1 tvg-id="{channel.get("id", "")}" tvg-name="{name}" tvg-logo="{channel.get("image", "")}" group-title="{category}",{name}\n')
                        f.write(f'#EXTVLCOPT:http-user-agent={HEADERS["User-Agent"]}\n')
                        f.write(f'#EXTVLCOPT:http-referrer={HEADERS["Referer"]}\n')
                        f.write(f"{url}\n\n")

        # 2. Filmler (TÜMÜ)
        print("\n🎬 Mevcut TÜM filmler taranıyor. Bu işlem uzun sürebilir...", file=sys.stderr)
        # Kategori listesi yerine doğrudan "Tüm Filmler" (filtre ID: 0) uç noktasını kullanıyoruz.
        all_movies_base_url = f"{MAIN_URL}/api/movie/by/filtres/0/created/"
        all_movies = get_all_pages(all_movies_base_url, "Tüm Filmler")
        
        # Filmleri kendi içinde kategorilere ayırarak yazdır
        movie_groups = {}
        for movie in all_movies:
            # Filmin kategorisini al, kategori yoksa "Diğer Filmler" olarak ata
            cat_name = movie.get('genres', 'Diğer Filmler').strip()
            if not cat_name: cat_name = "Diğer Filmler"
            if cat_name not in movie_groups: movie_groups[cat_name] = []
            movie_groups[cat_name].append(movie)

        for cat_name, movies in movie_groups.items():
            for movie in movies:
                for source in movie.get('sources', []):
                    if (url := source.get('url')) and isinstance(url, str) and url.endswith('.m3u8'):
                        name = movie.get('title', 'Bilinmeyen Film')
                        # Grup başlığını "Filmler" ana grubu ve alt kategori olarak düzenle
                        f.write(f'#EXTINF:-1 tvg-id="{movie.get("id", "")}" tvg-name="{name}" tvg-logo="{movie.get("image", "")}" group-title="Filmler;{cat_name}",{name}\n')
                        f.write(f'#EXTVLCOPT:http-user-agent={HEADERS["User-Agent"]}\n')
                        f.write(f'#EXTVLCOPT:http-referrer={HEADERS["Referer"]}\n')
                        f.write(f"{url}\n\n")
                        break # İlk m3u8 kaynağını bulunca diğer kaynakları arama

        # 3. Diziler (TÜMÜ)
        print("\n🎞️ Mevcut TÜM diziler taranıyor. Bu işlem de uzun sürebilir...", file=sys.stderr)
        # Kategori listesi yerine doğrudan "Tüm Diziler" (filtre ID: 0) uç noktasını kullanıyoruz.
        all_series_base_url = f"{MAIN_URL}/api/serie/by/filtres/0/created/"
        all_series = get_all_pages(all_series_base_url, "Tüm Diziler")
        
        # Tekrarlanan dizileri engellemek için ID'lerine göre benzersiz bir liste oluştur
        unique_series = list({s['id']: s for s in all_series if 'id' in s}.values())
        print(f"\nToplam {len(unique_series)} benzersiz dizi için bölümler taranıyor...", file=sys.stderr)
        
        # Her bir benzersiz dizi için bölüm bilgilerini çek
        for serie in tqdm(unique_series, desc="Dizi Bölümleri İşleniyor"):
            seasons = get_episodes_for_serie(serie)
            serie_name, serie_image = serie.get('title', 'Bilinmeyen Dizi'), serie.get('image', '')
            for season in seasons:
                for episode in season.get('episodes', []):
                    for source in episode.get('sources', []):
                        if (url := source.get('url')) and isinstance(url, str) and url.endswith('.m3u8'):
                            # Sezon ve bölüm numaralarını başlıktan temiz bir şekilde al
                            s_num = ''.join(filter(str.isdigit, season.get('title', ''))) or '0'
                            e_num = ''.join(filter(str.isdigit, episode.get('title', ''))) or '0'
                            ep_name = f"{serie_name} S{s_num.zfill(2)}E{e_num.zfill(2)}"
                            
                            # Grup başlığını "Diziler" ana grubu ve dizi adı olarak düzenle
                            f.write(f'#EXTINF:-1 tvg-id="{episode.get("id", "")}" tvg-name="{ep_name}" tvg-logo="{serie_image}" group-title="Diziler;{serie_name}",{ep_name}\n')
                            f.write(f'#EXTVLCOPT:http-user-agent={HEADERS["User-Agent"]}\n')
                            f.write(f'#EXTVLCOPT:http-referrer={HEADERS["Referer"]}\n')
                            f.write(f"{url}\n\n")
                            break # İlk m3u8 kaynağını bulunca döngüden çık

    print(f"\n✅ Playlist oluşturma başarıyla tamamlandı: {OUTPUT_FILENAME}", file=sys.stderr)

if __name__ == "__main__":
    generate_m3u()