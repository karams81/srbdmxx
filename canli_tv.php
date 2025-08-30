<?php
// Bu betik sadece CANLI YAYINLARI çeker ve canli_tv.m3u dosyasına yazar.

// --- BAŞLANGIÇ: Ortak Ayarlar ---
// Varsayılanlar (ikinci ihtimal)
$defaultBaseUrl = 'https://m.prectv49.sbs';
$defaultSuffix = '4F5A9C3D9A86FA54EACEDDD635185/c3c5bd17-e37b-4b94-a944-8a3688a30452/';
$defaultUserAgent = 'Dart/3.7 (dart:io)';
$defaultReferer = 'https://twitter.com/';
$pageCount = 4; // Canlı yayınlar için sayfa sayısı

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

// CANLI YAYINLARI ÇEK
echo "Canlı yayınlar çekiliyor...\n";
for ($page = 0; $page < $pageCount; $page++) {
    $apiUrl = $baseUrl . "/api/channel/by/filtres/0/0/$page/" . $suffix;
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
                    $categories = isset($content['categories']) && is_array($content['categories']) ? implode(", ", array_column($content['categories'], 'title')) : '';
                    
                    $m3uContent .= "#EXTINF:-1 tvg-id=\"{$content['id']}\" tvg-name=\"$title\" tvg-logo=\"$image\" group-title=\"$categories\", $title\n";
                    $m3uContent .= "#EXTVLCOPT:http-user-agent=googleusercontent\n";
                    $m3uContent .= "#EXTVLCOPT:http-referrer=https://twitter.com/\n";
                    $m3uContent .= "{$source['url']}\n";
                }
            }
        }
    }
}

// Dosyaya kaydet
file_put_contents('canli_tv.m3u', $m3uContent);
echo "Canlı yayınlar için M3U dosyası oluşturuldu: canli_tv.m3u\n";
?>