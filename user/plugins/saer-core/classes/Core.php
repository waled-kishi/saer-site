<?php
namespace Grav\Plugin\SaerCore;

use Grav\Common\Grav;
use MaxMind\Db\Reader;
use PDO;

/**
 * The saer-core service ($grav['saer_core']): download ids, visitor facts and recording.
 *
 * Privacy: no IP address and no user agent is stored. A visitor is a hash of
 * (day, IP, user agent) keyed with a secret kept on the server, so the same person is
 * counted once a day and cannot be followed from one day to the next. The only cookie is
 * the one set after someone fills the download form, so they are not asked again.
 */
class Core
{
    public const AGES = [
        'u18' => 'أقل من 18',
        '18-24' => '18 إلى 24',
        '25-34' => '25 إلى 34',
        '35-44' => '35 إلى 44',
        '45-54' => '45 إلى 54',
        '55+' => '55 فأكثر',
    ];
    public const GENDERS = ['m' => 'ذكر', 'f' => 'أنثى'];
    public const COOKIE = 'saer_dl';
    public const BOTS = '~bot|crawl|spider|slurp|facebookexternalhit|facebot|embedly|preview|whatsapp|telegrambot|'
        . 'curl|wget|python|httpclient|java/|go-http|headless|lighthouse|pingdom|uptime|monitor|scan|'
        . 'feedfetcher|mediapartners|bingpreview|ahrefs|semrush|mj12|petal|yandex|baidu|bytespider|gptbot|'
        . 'claude|anthropic|perplexity|ccbot|dataforseo|okhttp|axios|node-fetch|libwww|scrapy~i';

    private Grav $grav;
    private ?PDO $pdo = null;
    private ?array $countries = null;
    private ?string $ip = null;
    private ?string $geo = null;
    private ?string $secret = null;

    public function __construct(Grav $grav)
    {
        $this->grav = $grav;
    }

    public function pdo(): PDO
    {
        if (!$this->pdo) {
            $dir = $this->grav['locator']->findResource('user-data://', true, true) . '/saer-core';
            $this->pdo = Db::pdo($dir);
        }
        return $this->pdo;
    }

    /* ---------- files ---------- */

    /** Stable id for a page's media file (created on first use). */
    public function fileId(string $route, string $filename, string $label = ''): int
    {
        $pdo = $this->pdo();
        $st = $pdo->prepare('SELECT id, label FROM files WHERE route = ? AND filename = ?');
        $st->execute([$route, $filename]);
        if ($row = $st->fetch()) {
            if ($label !== '' && $label !== (string) $row['label']) {
                $pdo->prepare('UPDATE files SET label = ? WHERE id = ?')->execute([$label, $row['id']]);
            }
            return (int) $row['id'];
        }
        $pdo->prepare('INSERT OR IGNORE INTO files (route, filename, label, created) VALUES (?, ?, ?, ?)')
            ->execute([$route, $filename, $label, time()]);
        $st->execute([$route, $filename]);
        return (int) $st->fetchColumn();
    }

    public function file(int $id): ?array
    {
        $st = $this->pdo()->prepare('SELECT * FROM files WHERE id = ?');
        $st->execute([$id]);
        return $st->fetch() ?: null;
    }

    /* ---------- visitor facts ---------- */

    public function userAgent(): string
    {
        return (string) ($_SERVER['HTTP_USER_AGENT'] ?? '');
    }

    public function isBot(): bool
    {
        $ua = $this->userAgent();
        return $ua === '' || (bool) preg_match(self::BOTS, $ua);
    }

    /** The visitor's IP: first public address among the proxy headers, else REMOTE_ADDR. */
    public function ip(): string
    {
        if ($this->ip !== null) {
            return $this->ip;
        }
        $candidates = [];
        foreach (['HTTP_CF_CONNECTING_IP', 'HTTP_TRUE_CLIENT_IP', 'HTTP_X_REAL_IP', 'HTTP_X_FORWARDED_FOR', 'HTTP_X_CLIENT_IP'] as $h) {
            foreach (explode(',', (string) ($_SERVER[$h] ?? '')) as $v) {
                $candidates[] = trim($v);
            }
        }
        $candidates[] = (string) ($_SERVER['REMOTE_ADDR'] ?? '');
        foreach ($candidates as $c) {
            if ($c !== '' && filter_var($c, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE)) {
                return $this->ip = $c;
            }
        }
        return $this->ip = (string) ($_SERVER['REMOTE_ADDR'] ?? '');
    }

    /** ISO country code of the visitor ('' when unknown). */
    public function geo(): string
    {
        if ($this->geo !== null) {
            return $this->geo;
        }
        foreach (['HTTP_CF_IPCOUNTRY', 'HTTP_X_COUNTRY_CODE', 'HTTP_X_GEO_COUNTRY', 'HTTP_X_HCDN_COUNTRY', 'HTTP_X_COUNTRY'] as $h) {
            $v = strtoupper(trim((string) ($_SERVER[$h] ?? '')));
            if (preg_match('/^[A-Z]{2}$/', $v) && $v !== 'XX') {
                return $this->geo = $v;
            }
        }
        $db = __DIR__ . '/../data/dbip-country-lite.mmdb';
        if (is_file($db)) {
            try {
                $reader = new Reader($db);
                $rec = $reader->get($this->ip());
                $reader->close();
                $code = strtoupper((string) ($rec['country']['iso_code'] ?? ''));
                if (preg_match('/^[A-Z]{2}$/', $code)) {
                    return $this->geo = $code;
                }
            } catch (\Throwable $e) {
                // unknown country
            }
        }
        return $this->geo = '';
    }

    public function device(): string
    {
        $ua = $this->userAgent();
        if (preg_match('~iPad|Tablet|PlayBook|Silk|(Android(?!.*Mobile))~i', $ua)) {
            return 'tablet';
        }
        if (preg_match('~Mobi|iPhone|iPod|Android|Windows Phone|Opera Mini~i', $ua)) {
            return 'mobile';
        }
        return 'desktop';
    }

    /** Referring site (host without www./m./l.), '' for direct visits or our own pages. */
    public function referrer(): string
    {
        $ref = (string) ($_SERVER['HTTP_REFERER'] ?? '');
        $host = strtolower((string) parse_url($ref, PHP_URL_HOST));
        if ($host === '') {
            return '';
        }
        $own = strtolower((string) ($_SERVER['HTTP_HOST'] ?? ''));
        if ($host === $own) {
            return '';
        }
        $host = preg_replace('~^(www\.|m\.|l\.|lm\.|mobile\.)~', '', $host);
        $map = ['t.co' => 'x.com', 'twitter.com' => 'x.com', 'youtu.be' => 'youtube.com', 'fb.me' => 'facebook.com',
                'web.telegram.org' => 't.me', 'web.whatsapp.com' => 'whatsapp.com', 'wa.me' => 'whatsapp.com'];
        if (preg_match('~(^|\.)google\.~', $host)) {
            return 'google';
        }
        return $map[$host] ?? $host;
    }

    private function secret(): string
    {
        if ($this->secret !== null) {
            return $this->secret;
        }
        $this->pdo();
        $file = Db::dir() . '/secret';
        if (!is_file($file)) {
            @file_put_contents($file, bin2hex(random_bytes(32)));
            @chmod($file, 0600);
        }
        return $this->secret = trim((string) @file_get_contents($file)) ?: 'saer';
    }

    /** Same value for the same visitor all day; unrelated from one day to the next. */
    public function visitor(): string
    {
        return substr(hash_hmac('sha256', $this->today() . '|' . $this->ip() . '|' . $this->userAgent(), $this->secret()), 0, 16);
    }

    public function today(): string
    {
        return $this->now()->format('Y-m-d');
    }

    public function now(): \DateTimeImmutable
    {
        return new \DateTimeImmutable('now', new \DateTimeZone('Asia/Damascus'));
    }

    /* ---------- recording ---------- */

    public function recordView(string $route, string $title, string $template): void
    {
        $this->pdo()->prepare('INSERT INTO views (day, ts, route, title, template, visitor, geo, device, ref) VALUES (?,?,?,?,?,?,?,?,?)')
            ->execute([$this->today(), time(), $route, mb_substr($title, 0, 200), $template, $this->visitor(), $this->geo(),
                       $this->device(), $this->referrer()]);
    }

    public function recordDownload(array $file, ?int $profileId): void
    {
        $this->pdo()->prepare('INSERT INTO downloads (file_id, route, filename, profile_id, day, ts, visitor, geo, device, ref) VALUES (?,?,?,?,?,?,?,?,?,?)')
            ->execute([(int) $file['id'], $file['route'], $file['filename'], $profileId, $this->today(), time(), $this->visitor(),
                       $this->geo(), $this->device(), $this->referrer()]);
    }

    /* ---------- download form ---------- */

    public function countries(): array
    {
        if ($this->countries === null) {
            $this->countries = require __DIR__ . '/../data/countries.php';
        }
        return $this->countries;
    }

    public function countryName(string $code): string
    {
        $c = $this->countries();
        return $c['top'][$code] ?? $c['rest'][$code] ?? $code;
    }

    /** The profile behind the form cookie, if any. */
    public function profileFromCookie(): ?array
    {
        $token = (string) ($_COOKIE[self::COOKIE] ?? '');
        if (!preg_match('/^[a-f0-9]{32}$/', $token)) {
            return null;
        }
        $st = $this->pdo()->prepare('SELECT * FROM profiles WHERE token = ?');
        $st->execute([$token]);
        return $st->fetch() ?: null;
    }

    /** Validate posted form fields. Returns [clean values, errors]. */
    public function validateForm(array $post): array
    {
        $errors = [];
        $name = trim(preg_replace('/\s+/u', ' ', strip_tags((string) ($post['name'] ?? ''))));
        if (mb_strlen($name) < 2 || mb_strlen($name) > 80) {
            $errors['name'] = 'اكتب اسمك (حرفان على الأقل).';
        }
        $age = (string) ($post['age'] ?? '');
        if (!isset(self::AGES[$age])) {
            $errors['age'] = 'اختر الفئة العمرية.';
        }
        $country = strtoupper((string) ($post['country'] ?? ''));
        $c = $this->countries();
        if (!isset($c['top'][$country]) && !isset($c['rest'][$country])) {
            $errors['country'] = 'اختر البلد.';
        }
        $gender = (string) ($post['gender'] ?? '');
        if (!isset(self::GENDERS[$gender])) {
            $errors['gender'] = 'اختر الجنس.';
        }
        return [compact('name', 'age', 'country', 'gender'), $errors];
    }

    /** Signed render time, so a form posted back within a second (a bot) can be refused. */
    public function formStamp(): string
    {
        $t = (string) time();
        return $t . '.' . substr(hash_hmac('sha256', $t, $this->secret()), 0, 16);
    }

    public function stampOk(string $stamp): bool
    {
        [$t, $sig] = array_pad(explode('.', $stamp, 2), 2, '');
        if (!ctype_digit($t) || !hash_equals(substr(hash_hmac('sha256', $t, $this->secret()), 0, 16), $sig)) {
            return false;
        }
        $age = time() - (int) $t;
        return $age >= 2 && $age <= 86400;
    }

    /** At most 10 forms an hour from one visitor. */
    public function tooManyForms(): bool
    {
        $st = $this->pdo()->prepare('SELECT COUNT(*) FROM profiles WHERE visitor = ? AND created > ?');
        $st->execute([$this->visitor(), time() - 3600]);
        return (int) $st->fetchColumn() >= 10;
    }

    public function createProfile(array $v): array
    {
        $token = bin2hex(random_bytes(16));
        $this->pdo()->prepare('INSERT INTO profiles (token, name, age, country, gender, geo, visitor, created) VALUES (?,?,?,?,?,?,?,?)')
            ->execute([$token, $v['name'], $v['age'], $v['country'], $v['gender'], $this->geo(), $this->visitor(), time()]);
        $id = (int) $this->pdo()->lastInsertId();
        $secure = (($_SERVER['HTTPS'] ?? '') && $_SERVER['HTTPS'] !== 'off') || ($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https';
        setcookie(self::COOKIE, $token, ['expires' => time() + 30 * 86400, 'path' => '/', 'secure' => $secure,
                                          'httponly' => true, 'samesite' => 'Lax']);
        $_COOKIE[self::COOKIE] = $token;
        return ['id' => $id, 'token' => $token] + $v;
    }
}
