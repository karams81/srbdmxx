import json
import urllib.request
import urllib.error
import re
import os
import sys
from typing import Dict, List, Optional, Set

# API Konfigürasyon
DEFAULT_BASE_URL = 'https://m.prectv51.sbs'
SOURCE_URL = 'https://raw.githubusercontent.com/kerimmkirac/cs-kerim2/main/RecTV/src/main/kotlin/com/kerimmkirac/RecTV.kt'
API_KEY = '4F5A9C3D9A86FA54EACEDDD635185/c3c5bd17-e37b-4b94-a944-8a3688a30452'
SUFFIX = f'/{API_KEY}'

# Kullanıcı ayarları
USER_AGENT = 'googleusercontent'
REFERER = 'https://twitter.com/'

def is_base_url_working(base_url: str) -> bool:
    """Base URL'nin çalışıp çalışmadığını kontrol et"""
    if not base_url:
        return False
    test_url = f"{base_url}/api/channel/by/filtres/0/0/0{SUFFIX}"
    try:
        req = urllib.request.Request(
            test_url,
            headers={'User-Agent': 'okhttp/4.12.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200
    except:
        return False

def get_dynamic_base_url() -> str:
    """GitHub'dan dinamik olarak Base URL'yi al"""
    try:
        print("Güncel Base URL GitHub'dan alınıyor...", file=sys.stderr)
        with urllib.request.urlopen(SOURCE_URL, timeout=15) as response:
            content = response.read().decode('utf-8')
            if match := re.search(r'override\s+var\s+mainUrl\s*=\s*"([^"]+)"', content):
                url = match.group(1)
                print(f"GitHub'dan bulunan URL: {url}", file=sys.stderr)
                return url
    except Exception as e:
        print(f"GitHub'dan URL alınamadı: {e}", file=sys.stderr)
    return ""

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
    if not content.get('sources'):
        return ''

    for source in content['sources']:
        if source.get('type') == 'm3u8' and source.get('url'):
            title = content.get('title', '')
            image = content.get('image', '')
            content_id = content.get('id', '')

            m3u_lines.append(
                f'#EXTINF:-1 tvg-id="{content_id}" tvg-name="{title}" '
                f'tvg-logo="{image}" group-title="{category_name}",{title}\n'
                f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
                f'#EXTVLCOPT:http-referrer={REFERER}\n'
                f"{source['url']}\n"
            )
    return ''.join(m3u_lines)

# --- YENİ FONKSİYON BAŞLANGICI ---
def process_episode_content(episode: Dict, serie_title: str, serie_image: str) -> str:
    """Dizi bölümü verisini M3U formatına dönüştür"""
    m3u_lines = []
    if not episode.get('sources'):
        return ''

    for source in episode['sources']:
        if source.get('type') == 'm3u8' and source.get('url'):
            season_num = episode.get('season', 0)
            episode_num = episode.get('episode', 0)
            episode_title = episode.get('title', '')
            
            # Oynatıcıda görünecek başlığı formatla: Dizi Adı - S01E01 - Bölüm Adı
            full_title = f"{serie_title} - S{season_num:02d}E{episode_num:02d} - {episode_title}"
            
            # Bölüm için ana dizinin logosunu kullan
            image = serie_image
            content_id = episode.get('id', '')

            m3u_lines.append(
                f'#EXTINF:-1 tvg-id="{content_id}" tvg-name="{full_title}" '
                f'tvg-logo="{image}" group-title="{serie_title}",{full_title}\n'
                f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
                f'#EXTVLCOPT:http-referrer={REFERER}\n'
                f"{source['url']}\n"
            )
    return ''.join(m3u_lines)
# --- YENİ FONKSİYON SONU ---

def main():
    base_url = get_dynamic_base_url()
    if not is_base_url_working(base_url):
        print(f"Dinamik URL ({base_url}) çalışmıyor. Varsayılan URL deneniyor...", file=sys.stderr)
        base_url = DEFAULT_BASE_URL
    if not is_base_url_working(base_url):
        print("HATA: Hiçbir geçerli ve çalışan Base URL bulunamadı. Script sonlandırılıyor.", file=sys.stderr)
        sys.exit(1)

    print(f"Kullanılan Aktif Base URL: {base_url}", file=sys.stderr)

    m3u_content = ["#EXTM3U\n"]

    # CANLI YAYINLAR (0-3 arası sayfalar)
    print("Canlı yayınlar işleniyor...", file=sys.stderr)
    for page in range(4):
        url = f"{base_url}/api/channel/by/filtres/0/0/{page}{SUFFIX}"
        if data := fetch_data(url):
            for content in data:
                m3u_content.append(process_content(content, "Canlı Yayınlar"))

    # FİLMLER (Tüm kategoriler)
    print("Filmler işleniyor...", file=sys.stderr)
    movie_categories = {
        "0": "Son Filmler", "14": "Aile", "1": "Aksiyon", "13": "Animasyon",
        "19": "Belgesel Filmleri", "4": "Bilim Kurgu", "2": "Dram", "10": "Fantastik",
        "3": "Komedi", "8": "Korku", "17": "Macera", "5": "Romantik"
    }
    for category_id, category_name in movie_categories.items():
        print(f"- {category_name} kategorisi işleniyor.", file=sys.stderr)
        for page in range(8):
            url = f"{base_url}/api/movie/by/filtres/{category_id}/created/{page}{SUFFIX}"
            if data := fetch_data(url):
                for content in data:
                    m3u_content.append(process_content(content, category_name))

    # --- DEĞİŞTİRİLEN BÖLÜM BAŞLANGICI: DİZİLER ve BÖLÜMLERİ ---
    print("Diziler ve bölümleri işleniyor...", file=sys.stderr)
    
    # Önce tüm dizilerin listesini alalım
    series_list = []
    for page in range(8): # İlk 8 sayfadaki dizileri al
        url = f"{base_url}/api/serie/by/filtres/0/created/{page}{SUFFIX}"
        if data := fetch_data(url):
            series_list.extend(data)
        else:
            break # Veri gelmezse döngüyü kır

    # Şimdi her bir dizi için bölümlerini çekelim
    processed_series_ids = set()
    for serie in series_list:
        serie_id = serie.get('id')
        if not serie_id or serie_id in processed_series_ids:
            continue
        
        processed_series_ids.add(serie_id)
        serie_title = serie.get('title', 'Bilinmeyen Dizi')
        serie_image = serie.get('image', '')
        print(f"- '{serie_title}' dizisinin bölümleri alınıyor...", file=sys.stderr)
        
        # Bu diziye ait bölümlerin sayfalarını gez
        for page in range(20): # Bir dizide en fazla 20 sayfa bölüm olduğunu varsayalım
            episodes_url = f"{base_url}/api/episode/by/serie/{serie_id}/0/{page}{SUFFIX}"
            if episodes_data := fetch_data(episodes_url):
                if not episodes_data: # Sayfada bölüm yoksa bu dizi için aramayı bitir
                    break
                for episode in episodes_data:
                    m3u_content.append(process_episode_content(episode, serie_title, serie_image))
            else:
                break # Bölüm verisi alınamazsa sonraki diziye geç
    # --- DEĞİŞTİRİLEN BÖLÜM SONU ---

    # Dosyaya yaz
    output_filename = 'rectv_full.m3u'
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(''.join(m3u_content))
    print(f"\n'{output_filename}' dosyası başarıyla oluşturuldu!", file=sys.stderr)

if __name__ == "__main__":
    main()