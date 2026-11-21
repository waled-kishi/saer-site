<?php
namespace Grav\Plugin\SaerCore;

use Grav\Framework\Psr7\Response;
use Grav\Plugin\Api\Controllers\AbstractApiController;
use Grav\Plugin\Api\Exceptions\ValidationException;
use Grav\Plugin\Api\Response\ApiResponse;
use Grav\Plugin\SaerCore\Search;
use PDO;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

/**
 * Read-only statistics for the Admin2 page and dashboard widget.
 *   GET /saer-core/summary              today / 7 days, for the widget
 *   GET /saer-core/stats?days=30        everything the stats page shows
 *   GET /saer-core/export?type=people|downloads|views&days=30   CSV
 * All need api.system.read.
 */
class StatsController extends AbstractApiController
{
    private function core(): Core
    {
        return $this->grav['saer_core'];
    }

    private function page(string $route)
    {
        $pages = $this->grav['pages'];
        if (method_exists($pages, 'enablePages')) {
            $pages->enablePages();
        }
        return $pages->find($route);
    }

    private function pdo(): PDO
    {
        return $this->core()->pdo();
    }

    private function since(int $days): string
    {
        return $this->core()->now()->modify('-' . max(0, $days - 1) . ' days')->format('Y-m-d');
    }

    private function days(ServerRequestInterface $request): int
    {
        $d = (int) ($request->getQueryParams()['days'] ?? 30);
        return in_array($d, [1, 7, 30, 90, 365, 3650], true) ? $d : 30;
    }

    private function one(string $sql, array $args = []): array
    {
        $st = $this->pdo()->prepare($sql);
        $st->execute($args);
        return $st->fetch() ?: [];
    }

    private function all(string $sql, array $args = []): array
    {
        $st = $this->pdo()->prepare($sql);
        $st->execute($args);
        return $st->fetchAll();
    }

    private function totals(string $since): array
    {
        $v = $this->one('SELECT COUNT(*) AS views, COUNT(DISTINCT day || visitor) AS visitors FROM views WHERE day >= ?', [$since]);
        $d = $this->one('SELECT COUNT(*) AS downloads, COUNT(DISTINCT day || visitor || file_id) AS unique_downloads FROM downloads WHERE day >= ?', [$since]);
        $p = $this->one('SELECT COUNT(*) AS forms FROM profiles WHERE created >= ?', [strtotime($since . ' 00:00:00 Asia/Damascus')]);
        return array_map('intval', $v + $d + $p);
    }

    public function summary(ServerRequestInterface $request): ResponseInterface
    {
        $this->requirePermission($request, 'api.system.read');
        $today = $this->core()->today();
        $series = $this->all('SELECT day, COUNT(DISTINCT visitor) AS visitors, COUNT(*) AS views FROM views WHERE day >= ? GROUP BY day ORDER BY day', [$this->since(14)]);
        return ApiResponse::create([
            'today' => $this->totals($today),
            'week' => $this->totals($this->since(7)),
            'series' => $this->fillDays($series, 14, ['visitors', 'views']),
        ]);
    }

    public function stats(ServerRequestInterface $request): ResponseInterface
    {
        $this->requirePermission($request, 'api.system.read');
        $days = $this->days($request);
        $since = $this->since($days);
        $core = $this->core();

        $daily = $this->all('SELECT day, COUNT(*) AS views, COUNT(DISTINCT visitor) AS visitors FROM views WHERE day >= ? GROUP BY day', [$since]);
        $dlDaily = $this->all('SELECT day, COUNT(*) AS downloads FROM downloads WHERE day >= ? GROUP BY day', [$since]);
        $byDay = [];
        foreach ($daily as $r) {
            $byDay[$r['day']] = $r;
        }
        foreach ($dlDaily as $r) {
            $byDay[$r['day']] = ($byDay[$r['day']] ?? ['day' => $r['day']]) + ['downloads' => $r['downloads']];
        }
        $series = $this->fillDays(array_values($byDay), min($days, 365), ['views', 'visitors', 'downloads']);

        $pages = $this->all('SELECT route, MAX(title) AS title, COUNT(*) AS views, COUNT(DISTINCT day || visitor) AS visitors
            FROM views WHERE day >= ? GROUP BY route ORDER BY visitors DESC, views DESC LIMIT 50', [$since]);
        $sections = $this->all("SELECT CASE WHEN route = '/' THEN '/' ELSE '/' || substr(route, 2, instr(substr(route, 2) || '/', '/') - 1) END AS section,
            COUNT(*) AS views, COUNT(DISTINCT day || visitor) AS visitors FROM views WHERE day >= ? GROUP BY section ORDER BY visitors DESC", [$since]);

        $countries = $this->all('SELECT geo, COUNT(DISTINCT day || visitor) AS visitors FROM views WHERE day >= ? GROUP BY geo ORDER BY visitors DESC LIMIT 30', [$since]);
        foreach ($countries as &$c) {
            $c['name'] = $c['geo'] ? $core->countryName($c['geo']) : 'غير معروف';
        }
        unset($c);
        $devices = $this->all('SELECT device, COUNT(DISTINCT day || visitor) AS visitors FROM views WHERE day >= ? GROUP BY device ORDER BY visitors DESC', [$since]);
        $referrers = $this->all("SELECT CASE WHEN ref = '' OR ref IS NULL THEN '' ELSE ref END AS ref, COUNT(DISTINCT day || visitor) AS visitors
            FROM views WHERE day >= ? GROUP BY 1 ORDER BY visitors DESC LIMIT 20", [$since]);

        // Downloads per file, with what the form says about the people who downloaded it.
        $files = $this->all('SELECT d.file_id, d.route, d.filename, MAX(f.label) AS label, COUNT(*) AS downloads,
                COUNT(DISTINCT d.day || d.visitor) AS unique_downloads, COUNT(DISTINCT d.profile_id) AS people
            FROM downloads d LEFT JOIN files f ON f.id = d.file_id WHERE d.day >= ?
            GROUP BY d.file_id ORDER BY downloads DESC', [$since]);
        $titles = [];
        foreach ($files as &$f) {
            $route = $f['route'];
            if (!isset($titles[$route])) {
                $p = $this->page($route);
                $titles[$route] = $p ? (string) $p->title() : $route;
            }
            $f['book'] = $titles[$route];
            $f['ages'] = $this->breakdown('age', (int) $f['file_id'], $since);
            $f['genders'] = $this->breakdown('gender', (int) $f['file_id'], $since);
            $f['countries'] = $this->breakdown('country', (int) $f['file_id'], $since);
        }
        unset($f);

        $people = [
            'ages' => $this->profileBreakdown('age', $since),
            'genders' => $this->profileBreakdown('gender', $since),
            'countries' => $this->profileBreakdown('country', $since),
            'recent' => $this->recentPeople($since, 100),
        ];

        return ApiResponse::create([
            'days' => $days,
            'since' => $since,
            'totals' => $this->totals($since),
            'series' => $series,
            'pages' => array_map(fn($r) => ['route' => $r['route'], 'title' => $r['title'], 'views' => (int) $r['views'], 'visitors' => (int) $r['visitors']], $pages),
            'sections' => $sections,
            'countries' => $countries,
            'devices' => $devices,
            'referrers' => $referrers,
            'files' => $files,
            'people' => $people,
            'labels' => ['ages' => Core::AGES, 'genders' => Core::GENDERS],
        ]);
    }

    /** Form answers of the people who downloaded one file (each person once). */
    private function breakdown(string $field, int $fileId, string $since): array
    {
        $rows = $this->all("SELECT p.$field AS k, COUNT(DISTINCT p.id) AS n FROM downloads d JOIN profiles p ON p.id = d.profile_id
            WHERE d.file_id = ? AND d.day >= ? GROUP BY p.$field ORDER BY n DESC", [$fileId, $since]);
        return $this->label($field, $rows);
    }

    /** Form answers of everyone who downloaded anything in the period (each person once). */
    private function profileBreakdown(string $field, string $since): array
    {
        $rows = $this->all("SELECT p.$field AS k, COUNT(DISTINCT p.id) AS n FROM downloads d JOIN profiles p ON p.id = d.profile_id
            WHERE d.day >= ? GROUP BY p.$field ORDER BY n DESC", [$since]);
        return $this->label($field, $rows);
    }

    private function label(string $field, array $rows): array
    {
        foreach ($rows as &$r) {
            $r['n'] = (int) $r['n'];
            $r['label'] = match ($field) {
                'age' => Core::AGES[$r['k']] ?? $r['k'],
                'gender' => Core::GENDERS[$r['k']] ?? $r['k'],
                'country' => $this->core()->countryName((string) $r['k']),
                default => $r['k'],
            };
        }
        return $rows;
    }

    private function recentPeople(string $since, int $limit): array
    {
        $rows = $this->all('SELECT p.id AS profile_id, d.ts, d.route, d.filename, f.label, p.name, p.age, p.country, p.gender
            FROM downloads d JOIN profiles p ON p.id = d.profile_id LEFT JOIN files f ON f.id = d.file_id
            WHERE d.day >= ? ORDER BY d.ts DESC LIMIT ' . (int) $limit, [$since]);
        $titles = [];
        foreach ($rows as &$r) {
            if (!isset($titles[$r['route']])) {
                $p = $this->page($r['route']);
                $titles[$r['route']] = $p ? (string) $p->title() : $r['route'];
            }
            $r['book'] = $titles[$r['route']];
            $r['when'] = (new \DateTimeImmutable('@' . $r['ts']))->setTimezone(new \DateTimeZone('Asia/Damascus'))->format('Y-m-d H:i');
            $r['age'] = Core::AGES[$r['age']] ?? $r['age'];
            $r['gender'] = Core::GENDERS[$r['gender']] ?? $r['gender'];
            $r['country'] = $this->core()->countryName((string) $r['country']);
        }
        return $rows;
    }

    /** One entry per day for the last $days days, zeros where nothing happened. */
    private function fillDays(array $rows, int $days, array $keys): array
    {
        $by = [];
        foreach ($rows as $r) {
            $by[$r['day']] = $r;
        }
        $out = [];
        $start = $this->core()->now()->modify('-' . ($days - 1) . ' days');
        for ($i = 0; $i < $days; $i++) {
            $d = $start->modify("+$i days")->format('Y-m-d');
            $row = ['day' => $d];
            foreach ($keys as $k) {
                $row[$k] = (int) ($by[$d][$k] ?? 0);
            }
            $out[] = $row;
        }
        return $out;
    }

    /** DELETE /saer-core/profiles/{id}: remove one person's form answers and their downloads (spam, tests). */
    public function deleteProfile(ServerRequestInterface $request): ResponseInterface
    {
        $this->requirePermission($request, 'api.system.write');
        $id = (int) $this->getRouteParam($request, 'id');
        $pdo = $this->pdo();
        $pdo->prepare('DELETE FROM downloads WHERE profile_id = ?')->execute([$id]);
        $st = $pdo->prepare('DELETE FROM profiles WHERE id = ?');
        $st->execute([$id]);
        return ApiResponse::create(['deleted' => $st->rowCount()]);
    }

    /**
     * DELETE /saer-core/data?scope=views|all: start the statistics from zero.
     * views: page views (and the crawler list). all: also downloads and download-form answers.
     * Download ids (/dl/{id}) are kept so links keep working.
     */
    public function reset(ServerRequestInterface $request): ResponseInterface
    {
        $this->requirePermission($request, 'api.system.write');
        $scope = (string) ($request->getQueryParams()['scope'] ?? '');
        if (!in_array($scope, ['views', 'all'], true)) {
            throw new ValidationException('scope must be views or all');
        }
        $pdo = $this->pdo();
        $out = [];
        $pdo->beginTransaction();
        $out['views'] = $pdo->exec('DELETE FROM views');
        $pdo->exec('DELETE FROM crawlers');
        if ($scope === 'all') {
            $out['downloads'] = $pdo->exec('DELETE FROM downloads');
            $out['profiles'] = $pdo->exec('DELETE FROM profiles');
        }
        $pdo->commit();
        $pdo->exec('VACUUM');
        return ApiResponse::create(['scope' => $scope, 'deleted' => $out]);
    }

    /**
     * GET /saer-core/search: how the site search index is doing.
     */
    public function searchStatus(ServerRequestInterface $request): ResponseInterface
    {
        $this->requirePermission($request, 'api.system.read');
        $pdo = $this->pdo();
        Search::migrate($pdo);
        return ApiResponse::create([
            'engine' => Search::engine($pdo),
            'documents' => (int) $pdo->query('SELECT COUNT(*) FROM search_docs')->fetchColumn(),
            'updated' => (int) $pdo->query('SELECT COALESCE(MAX(updated), 0) FROM search_docs')->fetchColumn(),
        ]);
    }

    /**
     * POST /saer-core/search/rebuild: index every public page again from scratch.
     */
    public function searchRebuild(ServerRequestInterface $request): ResponseInterface
    {
        $this->requirePermission($request, 'api.system.write');
        $pages = $this->grav['pages'];
        if (method_exists($pages, 'enablePages')) {
            $pages->enablePages();
        }
        $started = microtime(true);
        $out = Search::rebuild($this->pdo(), $pages);
        $out['seconds'] = round(microtime(true) - $started, 1);
        return ApiResponse::create($out);
    }

    /** Downloadable kinds listed in the page panel (PDF/EPUB/ZIP are blocked for direct links). */
    private const FILE_EXT = ['pdf', 'epub', 'zip', 'docx', 'doc', 'odt', 'rtf', 'txt'];

    /**
     * GET /saer-core/files?route=/books/x: the page's downloadable files, including unpublished pages,
     * for the "ملفات الصفحة" panel in the page editor.
     */
    public function files(ServerRequestInterface $request): ResponseInterface
    {
        $this->requirePermission($request, 'api.pages.read');
        $page = $this->page('/' . trim((string) ($request->getQueryParams()['route'] ?? ''), '/'));
        if (!$page) {
            throw new ValidationException('page not found');
        }
        $out = [];
        foreach (glob($page->path() . '/*') ?: [] as $f) {
            $ext = strtolower(pathinfo($f, PATHINFO_EXTENSION));
            if (is_file($f) && in_array($ext, self::FILE_EXT, true)) {
                $out[] = ['name' => basename($f), 'ext' => $ext, 'size' => filesize($f), 'modified' => filemtime($f)];
            }
        }
        usort($out, fn($a, $b) => strcmp($a['name'], $b['name']));
        $h = (array) $page->header();
        return ApiResponse::create(['route' => $page->route(), 'title' => $page->title(),
            'published' => $page->published(), 'status' => $h['status'] ?? null, 'files' => $out]);
    }

    /** GET /saer-core/file?route=/books/x&name=file.pdf: the file itself (works for unpublished pages). */
    public function file(ServerRequestInterface $request): ResponseInterface
    {
        $this->requirePermission($request, 'api.pages.read');
        $q = $request->getQueryParams();
        $page = $this->page('/' . trim((string) ($q['route'] ?? ''), '/'));
        $name = basename((string) ($q['name'] ?? ''));
        $path = $page ? $page->path() . '/' . $name : '';
        $ext = strtolower(pathinfo($name, PATHINFO_EXTENSION));
        if (!$page || $name === '' || !in_array($ext, self::FILE_EXT, true) || !is_file($path)) {
            throw new ValidationException('file not found');
        }
        $types = ['pdf' => 'application/pdf', 'epub' => 'application/epub+zip', 'zip' => 'application/zip',
                  'docx' => 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                  'doc' => 'application/msword', 'odt' => 'application/vnd.oasis.opendocument.text',
                  'rtf' => 'application/rtf', 'txt' => 'text/plain; charset=utf-8'];
        return new Response(200, [
            'Content-Type' => $types[$ext],
            'Content-Length' => (string) filesize($path),
            'Content-Disposition' => "attachment; filename*=UTF-8''" . rawurlencode($name),
            'Cache-Control' => 'no-store',
        ], file_get_contents($path));
    }

    public function export(ServerRequestInterface $request): ResponseInterface
    {
        $this->requirePermission($request, 'api.system.read');
        $type = (string) ($request->getQueryParams()['type'] ?? 'people');
        $since = $this->since($this->days($request));
        $core = $this->core();
        $tz = new \DateTimeZone('Asia/Damascus');
        $when = fn($ts) => (new \DateTimeImmutable('@' . $ts))->setTimezone($tz)->format('Y-m-d H:i');

        if ($type === 'views') {
            $head = ['اليوم', 'الصفحة', 'العنوان', 'الزيارات', 'الزوار'];
            $rows = array_map(fn($r) => array_values($r), $this->all('SELECT day, route, MAX(title), COUNT(*), COUNT(DISTINCT visitor)
                FROM views WHERE day >= ? GROUP BY day, route ORDER BY day DESC, 5 DESC', [$since]));
        } elseif ($type === 'downloads') {
            $head = ['الوقت', 'الكتاب', 'الملف', 'الاسم', 'العمر', 'البلد', 'الجنس', 'بلد الاتصال', 'الجهاز'];
            $rows = [];
            foreach ($this->all('SELECT d.ts, d.route, COALESCE(f.label, d.filename) AS file, p.name, p.age, p.country, p.gender, d.geo, d.device
                FROM downloads d LEFT JOIN profiles p ON p.id = d.profile_id LEFT JOIN files f ON f.id = d.file_id
                WHERE d.day >= ? ORDER BY d.ts DESC', [$since]) as $r) {
                $page = $this->page($r['route']);
                $rows[] = [$when($r['ts']), $page ? $page->title() : $r['route'], $r['file'], $r['name'] ?? '',
                           Core::AGES[$r['age'] ?? ''] ?? '', $r['country'] ? $core->countryName($r['country']) : '',
                           Core::GENDERS[$r['gender'] ?? ''] ?? '', $r['geo'] ? $core->countryName($r['geo']) : '', $r['device']];
            }
        } else {
            $type = 'people';
            $head = ['تاريخ التعبئة', 'الاسم', 'العمر', 'البلد', 'الجنس', 'عدد التحميلات', 'الكتب'];
            $rows = [];
            foreach ($this->all("SELECT p.id, p.created, p.name, p.age, p.country, p.gender, COUNT(d.id) AS n, GROUP_CONCAT(DISTINCT d.route) AS routes
                FROM profiles p LEFT JOIN downloads d ON d.profile_id = p.id WHERE p.created >= ? GROUP BY p.id ORDER BY p.created DESC",
                [strtotime($since . ' 00:00:00 Asia/Damascus')]) as $r) {
                $books = [];
                foreach (array_filter(explode(',', (string) $r['routes'])) as $route) {
                    $page = $this->page($route);
                    $books[] = $page ? $page->title() : $route;
                }
                $rows[] = [$when($r['created']), $r['name'], Core::AGES[$r['age']] ?? $r['age'], $core->countryName($r['country']),
                           Core::GENDERS[$r['gender']] ?? $r['gender'], $r['n'], implode('، ', $books)];
            }
        }

        $fh = fopen('php://temp', 'w+');
        fwrite($fh, "\xEF\xBB\xBF"); // BOM so Excel reads Arabic
        fputcsv($fh, $head, ',', '"', '\\');
        foreach ($rows as $row) {
            fputcsv($fh, $row, ',', '"', '\\');
        }
        rewind($fh);
        $csv = stream_get_contents($fh);
        fclose($fh);
        return new Response(200, [
            'Content-Type' => 'text/csv; charset=utf-8',
            'Content-Disposition' => 'attachment; filename="saer-' . $type . '-' . $since . '.csv"',
            'Cache-Control' => 'no-store',
        ], $csv);
    }
}
