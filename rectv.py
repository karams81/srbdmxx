import json
import urllib.request
import urllib.error
import re
import os
import sys
from typing import Dict, List, Optional, Set

# API Konfigürasyon
SOURCE_URL = 'https://raw.githubusercontent.com/kerimmkirac/cs-kerim2/main/RecTV/src/main/kotlin/com/kerimmkirac/RecTV.kt'
API_KEY = '4F5A9C3D9A86FA54EACEDDD635185/c3c5bd17-e37b-4b94-a944-8a3688a30452'
SUFFIX = f'/{API_KEY}'

# Kullanıcı ayarları
USER_AGENT = 'googleusercontent'
REFERER = 'https://twitter.com/'

def is_base_url_working(base_url: str) -> bool:
    """Base URL'nin çalışıp çalışmadığını ve içerik barındırdığını kontrol et"""
    if not base_url:
        return False
    # Sadece 200 OK dönmesi yetmez, içinde veri olduğundan da emin olalım.
    test_url = f"{base_url}/api/channel/by/filtres/0/0/0{SUFFIX}"
    try:
        req = urllib.request.Request(
            test_url,
            headers={'User-Agent': 'okhttp/4.12.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                # Dönen verinin boş bir liste olmadığını kontrol et
                data = json.loads(response.read().decode('utf-8'))
                return isinstance(data, list) and len(data) > 0
            return False
    except:
        return False

def get_dynamic_base_url() -> str:
    """GitHub'dan dinamik olarak Base URL'yi al"""
    try:
        print("Güncel Base URL GitHub'dan deneniyor...", file=sys.stderr)
        with urllib.request.urlopen(SOURCE_URL, timeout=15) as response:
            content = response.read().decode('utf-8')
            if match := re.search(r'override\s+var\s+mainUrl\s*=\s*"([^"]+)"', content):
                url = match.group(1)
                print(f"GitHub'dan bulunan URL: {url}", file=sys.stderr)
                return url
    except Exception as e:
        print(f"GitHub'dan URL alınamadı: {e}", file=sys.stderr)
    return ""

def find_working_base_url() -> str:
    """Çalışan ve içerik barındıran ilk base URL'yi bulur."""
    # 1. Öncelik: GitHub'daki dinamik URL
    dynamic_url = get_dynamic_base_url()
    if is_base_url_working(dynamic_url):
        return dynamic_url
    print(f"Dinamik URL ({dynamic_url}) çalışmıyor veya boş. Alternatifler denenecek.", file=sys.stderr)

    # 2. Öncelik: Potansiyel domain listesi
    # Kullanıcının belirttiği gibi 49, 51, 53 gibi varyasyonları deneyelim
    for i in range(48, 56): # prectv48.sbs'den prectv55.sbs'e kadar dener
        potential_url = f"https://m.prectv{i}.sbs"
        print(f"Potansiyel URL deneniyor: {potential_url}", file=sys.stderr)
        if is_base_url_working(potential_url):
            return potential_url
            
    return "" # Hiçbiri çalışmazsa boş döner

def fetch_data(url: str) -> Optional[List[Dict]]:
    """API'den veri çek"""
    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': USER_AGENT,
                'Referer': REFERER
            }
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"API hatası ({url}): {e}", file=sys.stderr)
        return None

def process_content(content: Dict, category_name: str) -> str:
    """İçeriği (Canlı TV/Film) M3U formatına dönüştür"""
    m3u_lines = []
    if not content.get('sources'): return ''
    for source in content['sources']:
        if source.get('type') == 'm3u8' and source.get('url'):
            title = content.get('title', ''); image = content.get('image', ''); content_id = content.get('id', '')
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{content_id}" tvg-name="{title}" tvg-logo="{image}" group-title="{category_name}",{title}\n#EXTVLCOPT:http-user-agent={USER_AGENT}\n#EXTVLCOPT:http-referrer={REFERER}\n{source["url"]}\n')
    return ''.join(m3u_lines)

def process_episode_content(episode: Dict, serie_title: str, serie_image: str) -> str:
    """Dizi bölümü verisini M3U formatına dönüştürürken hiyerarşik gruplama yapar."""
    m3u_lines = []
    if not episode.get('sources'): return ''
    for source in episode['sources']:
        if source.get('type') == 'm3u8' and source.get('url'):
            season_num = episode.get('season', 0); episode_num = episode.get('episode', 0); episode_title = episode.get('title', '')
            full_title = f"{serie_title} - S{season_num:02d}E{episode_num:02d} - {episode_title}"
            image = serie_image; content_id = episode.get('id', '')
            group_title = f"Diziler;{serie_title}"
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{content_id}" tvg-name="{full_title}" tvg-logo="{image}" group-title="{group_title}",{full_title}\n#EXTVLCOPT:http-user-agent={USER_AGENT}\n#EXTVLCOPT:http-referrer={REFERER}\n{source["url"]}\n')
    return ''.join(m3u_lines)

def main():
    base_url = find_working_base_url()
    if not base_url:
        print("HATA: Çalışan ve içerik barındıran hiçbir Base URL bulunamadı. Script sonlandırılıyor.", file=sys.stderr)
        sys.exit(1)

    print(f"Kullanılan Aktif Base URL: {base_url}", file=sys.stderr)
    m3u_content = ["#EXTM3U\n"]

    # --- DERİN TARAMA: CANLI YAYINLAR ---
    print("Canlı yayınlar taranıyor (Tüm sayfalar)...", file=sys.stderr)
    page = 0
    while True:
        url = f"{base_url}/api/channel/by/filtres/0/0/{page}{SUFFIX}"
        if not (data := fetch_data(url)): break
        for content in data:
            m3u_content.append(process_content(content, "Canlı Yayınlar"))
        print(f"\rCanlı Yayınlar: Sayfa {page+1} işlendi...", end="", file=sys.stderr)
        page += 1
    print("\nCanlı yayın taraması tamamlandı.", file=sys.stderr)

    # --- DERİN TARAMA: FİLMLER ---
    print("Filmler taranıyor (Tüm kategoriler ve sayfalar)...", file=sys.stderr)
    movie_categories = {"0": "Son Filmler", "14": "Aile", "1": "Aksiyon", "13": "Animasyon", "19": "Belgesel Filmleri", "4": "Bilim Kurgu", "2": "Dram", "10": "Fantastik", "3": "Komedi", "8": "Korku", "17": "Macera", "5": "Romantik"}
    for category_id, category_name in movie_categories.items():
        print(f"- Kategori: {category_name}", file=sys.stderr)
        page = 0
        while True:
            url = f"{base_url}/api/movie/by/filtres/{category_id}/created/{page}{SUFFIX}"
            if not (data := fetch_data(url)): break
            for content in data:
                m3u_content.append(process_content(content, category_name))
            print(f"\r  '{category_name}': Sayfa {page+1} işlendi...", end="", file=sys.stderr)
            page += 1
        print("\n  Kategori tamamlandı.", file=sys.stderr)
    print("Film taraması tamamlandı.", file=sys.stderr)

    # --- DERİN TARAMA: DİZİLER ve BÖLÜMLERİ ---
    print("Diziler ve bölümleri taranıyor (Tüm sayfalar)...", file=sys.stderr)
    series_list = []
    page = 0
    while True:
        url = f"{base_url}/api/serie/by/filtres/0/created/{page}{SUFFIX}"
        if not (data := fetch_data(url)): break
        series_list.extend(data)
        print(f"\rDizi listesi alınıyor: Sayfa {page+1} işlendi...", end="", file=sys.stderr)
        page += 1
    print(f"\nToplam {len(series_list)} dizi bulundu. Bölümler taranıyor...", file=sys.stderr)

    processed_series_ids = set()
    for i, serie in enumerate(series_list):
        serie_id = serie.get('id')
        if not serie_id or serie_id in processed_series_ids: continue
        processed_series_ids.add(serie_id)
        serie_title = serie.get('title', 'Bilinmeyen Dizi')
        serie_image = serie.get('image', '')
        print(f"[{i+1}/{len(series_list)}] '{serie_title}' bölümleri alınıyor...", file=sys.stderr)
        
        episode_page = 0
        while True:
            episodes_url = f"{base_url}/api/episode/by/serie/{serie_id}/0/{episode_page}{SUFFIX}"
            if not (episodes_data := fetch_data(episodes_url)): break
            for episode in episodes_data:
                m3u_content.append(process_episode_content(episode, serie_title, serie_image))
            episode_page += 1
    print("Dizi ve bölüm taraması tamamlandı.", file=sys.stderr)

    # Dosyaya yaz
    output_filename = 'rectv_full.m3u'
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(''.join(m3u_content))
    print(f"\n'{output_filename}' dosyası başarıyla oluşturuldu!", file=sys.stderr)

if __name__ == "__main__":
    main()