<?php
// Bu betik sadece FİLMLERİ çeker ve filmler.m3u dosyasına yazar.

// --- BAŞLANGIÇ: Ortak Ayarlar ---
// Varsayılanlar (ikinci ihtimal)
$defaultBaseUrl = 'https://m.prectv49.sbs';
$defaultSuffix = '4F5A9C3D9A86FA54EACEDDD635185/c3c5bd17-e37b-4b94-a944-8a3688a30452/';
$defaultUserAgent = 'Dart/3.7 (dart:io)';
$defaultReferer = 'https://twitter.com/';

// Github kaynak dosyası (ilk ihtimal)
$sourceUrlRaw = 'https://raw.githubusercontent.com/kerimmkirac/cs-kerim2/main/RecTV/src/main/kotlin/com/kerimmkirac/RecTV.kt';
$proxyUrl = 'https://api.codetabs.com/v1/proxy/?quest=' . urlencode($sourceUrlRaw);

// Güncel değerlerin tutulacağı değişkenler
$baseUrl    = $defaultBaseUrl;
$suffix     = $defaultSuffix;
$userAgent  = $defaultUserAgent;
$referer    = $defaultReferer;

// Github içeriğini çekmek için fonksiyon
function fetchGithubContent($sourceUrlRaw, $proxyUrl) {
    $githubContent = @file_get_contents($sourceUrlRaw);
    if ($githubContent !== FALSE) return $githubContent;
    return @file_get_contents($proxyUrl);
}

$githubContent = fetchGithubContent($sourceUrlRaw, $proxyUrl);

// Regex ile değerleri çek
if ($githubContent !== FALSE) {
    if (preg_match('/override\s+var\s+mainUrl\s*=\s*"([^"]+)"/', $githubContent, $m)) $baseUrl = $m[1];
    if (preg_match('/private\s+val\s+swKey\s*=\s*"([^"]+)"/', $githubContent, $m)) $suffix = $m[1];
    if (preg_match('/user-agent"\s*to\s*"([^"]+)"/', $githubContent, $m)) $userAgent = $m[1];
    if (preg_match('/Referer"\s*to\s*"([^"]+)"/', $githubContent, $m)) $referer = $m[1];
}

// URL'nin çalışıp çalışmadığını kontrol et
function isBaseUrlWorking($baseUrl, $suffix, $userAgent) {
    $testUrl = $baseUrl . '/api/channel/by/filtres/0/0/0/' . $suffix;
    $opts = ['http' => ['header' => "User-Agent: $userAgent\r\n"]];
    $ctx = stream_context_create($opts);
    return @file_get_contents($testUrl, false, $ctx) !== FALSE;
}
if (!isBaseUrlWorking($baseUrl, $suffix, $userAgent)) {
    $baseUrl = $defaultBaseUrl;
    $suffix = $defaultSuffix;
}

// API çağrıları için HTTP context oluştur
$options = ['http' => ['header' => "User-Agent: $userAgent\r\nReferer: $referer\r\n"]];
$context = stream_context_create($options);
// --- BİTİŞ: Ortak Ayarlar ---

// M3U Çıktısı Oluştur
$m3uContent = "#EXTM3U\n";

// FİLMLERİ ÇEK
echo "Filmler çekiliyor...\n";
$movieApis = [
    "api/movie/by/filtres/0/created/SAYFA/$suffix"   => "Son Filmler",
    "api/movie/by/filtres/14/created/SAYFA/$suffix"  => "Aile",
    "api/movie/by/filtres/1/created/SAYFA/$suffix"   => "Aksiyon",
    "api/movie/by/filtres/13/created/SAYFA/$suffix"  => "Animasyon",
    "api/movie/by/filtres/19/created/SAYFA/$suffix"  => "Belgesel Filmleri",
    "api/movie/by/filtres/4/created/SAYFA/$suffix"   => "Bilim Kurgu",
    "api/movie/by/filtres/2/created/SAYFA/$suffix"   => "Dram",
    "api/movie/by/filtres/10/created/SAYFA/$suffix"  => "Fantastik",
    "api/movie/by/filtres/3/created/SAYFA/$suffix"   => "Komedi",
    "api/movie/by/filtres/8/created/SAYFA/$suffix"   => "Korku",
    "api/movie/by/filtres/17/created/SAYFA/$suffix"  => "Macera",
    "api/movie/by/filtres/5/created/SAYFA/$suffix"   => "Romantik",
];
foreach ($movieApis as $movieApi => $categoryName) {
    echo "- '$categoryName' kategorisi işleniyor...\n";
    for ($page = 0; $page <= 25; $page++) {
        $apiUrl = $baseUrl . '/' . str_replace('SAYFA', $page, $movieApi);
        $response = @file_get_contents($apiUrl, false, $context);
        if ($response === FALSE) continue;
        $data = json_decode($response, true);
        if ($data === null) continue;

        foreach ($data as $content) {
            if (isset($content['sources']) && is_array($content['sources'])) {
                foreach ($content['sources'] as $source) {
                    if (($source['type'] ?? '') === 'm3u8' && isset($source['url'])) {
                        $title = $content['title'] ?? '';
                        $image = isset($content['image']) ? ((strpos($content['image'], 'http') === 0) ? $content['image'] : $baseUrl . '/' . ltrim($content['image'], '/')) : '';
                        $m3uContent .= "#EXTINF:-1 tvg-id=\"{$content['id']}\" tvg-name=\"$title\" tvg-logo=\"$image\" group-title=\"$categoryName\", $title\n";
                        $m3uContent .= "#EXTVLCOPT:http-user-agent=googleusercontent\n";
                        $m3uContent .= "#EXTVLCOPT:http-referrer=https://twitter.com/\n";
                        $m3uContent .= "{$source['url']}\n";
                    }
                }
            }
        }
    }
}

// Dosyaya kaydet
file_put_contents('filmler.m3u', $m3uContent);
echo "Filmler için M3U dosyası oluşturuldu: filmler.m3u\n";
?>
