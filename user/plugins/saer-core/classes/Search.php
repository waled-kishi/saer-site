<?php
namespace Grav\Plugin\SaerCore;

use PDO;
use Throwable;

/**
 * Site search for visitors: a SQLite full-text index of the published pages,
 * kept in the same database as the rest of saer-core.
 *
 * Arabic is normalized before indexing and before searching, so "الايمان"
 * finds "الإيمان" and "صلاه" finds "صلاة". The normalization maps one letter
 * to another letter of the same byte length, so an offset in the normalized
 * text is also an offset in the original text, which is how the result
 * snippets are cut out of the original wording.
 *
 * Diacritics (harakat) are handled by the FTS5 tokenizer itself
 * (remove_diacritics 2), so a search for "الحمد" matches "الْحَمْدُ".
 *
 * Tables
 *   search_docs  one row per page: title, section, date and the original text
 *   search_fts   the FTS5 index over the normalized title and text
 */
class Search
{
    /** Letters folded together. Every pair is the same length in bytes. */
    private const FOLD = [
        'أ' => 'ا', 'إ' => 'ا', 'آ' => 'ا', 'ٱ' => 'ا',
        'ة' => 'ه', 'ى' => 'ي', 'ؤ' => 'و', 'ئ' => 'ي',
    ];

    private static ?bool $fts = null;

    /** Whether this SQLite build has FTS5; without it the search falls back to LIKE. */
    public static function hasFts(PDO $pdo): bool
    {
        if (self::$fts === null) {
            try {
                $pdo->exec('CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5('
                    . 'route UNINDEXED, title, body, tokenize="unicode61 remove_diacritics 2")');
                self::$fts = true;
            } catch (Throwable $e) {
                self::$fts = false;
            }
        }
        return self::$fts;
    }

    public static function engine(PDO $pdo): string
    {
        return self::hasFts($pdo) ? 'fts5' : 'like';
    }

    public static function migrate(PDO $pdo): void
    {
        $pdo->exec(<<<SQL
            CREATE TABLE IF NOT EXISTS search_docs (
                route TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                parent TEXT,
                section TEXT,
                template TEXT,
                date INTEGER,
                summary TEXT,
                body TEXT NOT NULL,
                body_n TEXT NOT NULL,
                updated INTEGER NOT NULL
            );
        SQL);
        self::hasFts($pdo);
    }

    /**
     * Fold the letters a reader types differently onto one shape, without
     * changing the length of the string.
     */
    public static function normalize(string $text): string
    {
        $text = strtr($text, self::FOLD);
        return strtolower($text);
    }

    /** Harakat, tatweel and the Quranic marks, dropped from a search query. */
    public static function stripMarks(string $text): string
    {
        return (string) preg_replace('/[\x{0610}-\x{061A}\x{064B}-\x{065F}\x{0640}\x{0670}\x{06D6}-\x{06ED}]/u', '', $text);
    }

    /** The words of a query, normalized and stripped of anything FTS5 would read as syntax. */
    public static function terms(string $q): array
    {
        $q = self::normalize(self::stripMarks($q));
        $q = (string) preg_replace('/[^\p{L}\p{N}\s]+/u', ' ', $q);
        $terms = preg_split('/\s+/u', trim($q), -1, PREG_SPLIT_NO_EMPTY) ?: [];
        $terms = array_filter($terms, static fn($t) => mb_strlen($t) > 1);
        return array_slice(array_values($terms), 0, 8);
    }

    /**
     * The same word with and without the definite article, so "صلاه" finds
     * "الصلاة" and "الايمان" finds "إيمان".
     */
    public static function variants(string $term): array
    {
        $out = [$term];
        if (mb_strpos($term, 'ال') === 0 && mb_strlen($term) > 3) {
            $out[] = mb_substr($term, 2);
        } elseif (mb_strpos($term, 'وال') === 0 && mb_strlen($term) > 4) {
            $out[] = mb_substr($term, 3);
        } else {
            $out[] = 'ال' . $term;
        }
        return $out;
    }

    /* ---------------- indexing ---------------- */

    /** True when the page belongs in the index (what a visitor can actually open). */
    public static function indexable($page): bool
    {
        if (!$page || !$page->routable() || !$page->published()) {
            return false;
        }
        if (in_array($page->template(), ['error', 'search', 'saer-download'], true)) {
            return false;
        }
        for ($p = $page; $p; $p = $p->parent()) {
            if (($p->header()->coming_soon ?? false)) {
                return false;
            }
        }
        return true;
    }

    public static function removeRoute(PDO $pdo, string $route): void
    {
        $st = $pdo->prepare('DELETE FROM search_docs WHERE route = ?');
        $st->execute([$route]);
        if (self::hasFts($pdo)) {
            $st = $pdo->prepare('DELETE FROM search_fts WHERE route = ?');
            $st->execute([$route]);
        }
    }

    /** Index one page (or drop it from the index when it is no longer public). */
    public static function indexPage(PDO $pdo, $page): bool
    {
        $route = (string) ($page && $page->home() ? '/' : ($page ? $page->route() : ''));
        if ($route === '') {
            return false;
        }
        if (!self::indexable($page)) {
            self::removeRoute($pdo, $route);
            return false;
        }

        $h = $page->header();
        $title = (string) $page->title();
        $summary = trim((string) ($h->summary ?? ''));
        $parts = [$summary, (string) ($h->written ?? ''), (string) ($h->location ?? ''), (string) $page->rawMarkdown()];
        $body = self::plain(implode("\n", array_filter(array_map('trim', $parts))));

        // The section is the top-level page this one sits under ("خطب الجمعة"...)
        $top = $page;
        $parent = $page->parent();
        while ($parent && !$parent->home() && $parent->parent()) {
            $top = $parent;
            $parent = $parent->parent();
        }
        $section = $top && $top !== $page ? (string) $top->title() : '';
        $near = $page->parent();
        $nearTitle = $near && !$near->home() && $near !== $top ? (string) $near->title() : '';

        self::removeRoute($pdo, $route);
        $st = $pdo->prepare('INSERT INTO search_docs (route, title, parent, section, template, date, summary, body, body_n, updated)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)');
        $st->execute([$route, $title, $nearTitle, $section, (string) $page->template(),
                      (int) $page->date(), $summary, $body,
                      self::normalize(self::stripMarks($title . "\n" . $body)), time()]);
        if (self::hasFts($pdo)) {
            $st = $pdo->prepare('INSERT INTO search_fts (route, title, body) VALUES (?, ?, ?)');
            $st->execute([$route, self::normalize($title), self::normalize($title . "\n" . $body)]);
        }
        return true;
    }

    /** Rebuild the whole index from the page tree. */
    public static function rebuild(PDO $pdo, $pages): array
    {
        self::migrate($pdo);
        $pdo->beginTransaction();
        $pdo->exec('DELETE FROM search_docs');
        if (self::hasFts($pdo)) {
            $pdo->exec('DELETE FROM search_fts');
        }
        $count = 0;
        foreach ($pages->all() as $page) {
            if (self::indexPage($pdo, $page)) {
                $count++;
            }
        }
        $pdo->commit();
        return ['engine' => self::engine($pdo), 'indexed' => $count];
    }

    /** The words themselves, without the markdown and twig scaffolding. */
    private static function plain(string $raw): string
    {
        $raw = (string) preg_replace('/\{%.*?%\}|\{\{.*?\}\}|\[\w+[^\]]*\].*?\[\/\w+\]/us', ' ', $raw);
        $raw = (string) preg_replace('/!?\[([^\]]*)\]\([^)]*\)/u', '$1', $raw);
        $raw = (string) preg_replace('/[#>*_`~|-]+/u', ' ', $raw);
        $raw = strip_tags($raw);
        return trim((string) preg_replace('/[ \t]*\R[ \t]*/u', "\n", (string) preg_replace('/[ \t]+/u', ' ', $raw)));
    }

    /* ---------------- searching ---------------- */

    /**
     * @return array{total:int, results:array<int,array<string,mixed>>}
     */
    public static function query(PDO $pdo, string $q, int $limit = 20, int $offset = 0): array
    {
        $terms = self::terms($q);
        if (!$terms) {
            return ['total' => 0, 'results' => []];
        }

        if (self::hasFts($pdo)) {
            $match = implode(' AND ', array_map(static function ($t) {
                $or = array_map(static fn($v) => '"' . $v . '"*', self::variants($t));
                return '(' . implode(' OR ', $or) . ')';
            }, $terms));
            $total = (int) self::scalar($pdo, 'SELECT COUNT(*) FROM search_fts WHERE search_fts MATCH ?', [$match]);
            $sql = 'SELECT d.* FROM search_fts JOIN search_docs d ON d.route = search_fts.route
                    WHERE search_fts MATCH ? ORDER BY bm25(search_fts, 0.0, 12.0, 1.0) LIMIT ? OFFSET ?';
            $st = $pdo->prepare($sql);
            $st->bindValue(1, $match);
            $st->bindValue(2, $limit, PDO::PARAM_INT);
            $st->bindValue(3, $offset, PDO::PARAM_INT);
            $st->execute();
            $rows = $st->fetchAll();
        } else {
            $where = [];
            $args = [];
            foreach ($terms as $t) {
                $vs = self::variants($t);
                $where[] = '(' . implode(' OR ', array_fill(0, count($vs), 'dn LIKE ?')) . ')';
                foreach ($vs as $v) {
                    $args[] = '%' . $v . '%';
                }
            }
            $where = implode(' AND ', $where);
            $base = 'FROM (SELECT *, body_n AS dn FROM search_docs) WHERE ' . $where;
            $total = (int) self::scalar($pdo, 'SELECT COUNT(*) ' . $base, $args);
            $st = $pdo->prepare('SELECT * ' . $base . ' ORDER BY length(body) ASC LIMIT ? OFFSET ?');
            foreach ($args as $i => $a) {
                $st->bindValue($i + 1, $a);
            }
            $st->bindValue(count($args) + 1, $limit, PDO::PARAM_INT);
            $st->bindValue(count($args) + 2, $offset, PDO::PARAM_INT);
            $st->execute();
            $rows = $st->fetchAll();
        }

        $results = [];
        foreach ($rows as $row) {
            $results[] = [
                'route' => $row['route'],
                'title' => $row['title'],
                'parent' => $row['parent'],
                'section' => $row['section'],
                'template' => $row['template'],
                'date' => (int) $row['date'],
                'snippet' => self::snippet((string) $row['body'] ?: (string) $row['summary'], $terms),
            ];
        }
        return ['total' => $total, 'results' => $results];
    }

    private static function scalar(PDO $pdo, string $sql, array $args)
    {
        $st = $pdo->prepare($sql);
        $st->execute($args);
        return $st->fetchColumn();
    }

    /**
     * A window of the original text around the first match, with the matching
     * words wrapped in <mark>. Everything else is escaped.
     */
    public static function snippet(string $body, array $terms, int $chars = 190): string
    {
        $body = trim((string) preg_replace('/\s+/u', ' ', $body));
        if ($body === '') {
            return '';
        }
        $needles = [];
        foreach ($terms as $t) {
            foreach (self::variants($t) as $v) {
                $needles[] = $v;
            }
        }
        $needles = array_unique($needles);
        usort($needles, static fn($a, $b) => mb_strlen($b) <=> mb_strlen($a));

        $hay = self::normalize(self::stripMarksKeepLength($body));
        $at = false;
        foreach ($needles as $v) {
            $pos = mb_strpos($hay, $v);
            if ($pos !== false && ($at === false || $pos < $at)) {
                $at = $pos;
            }
        }
        $start = $at === false ? 0 : max(0, $at - (int) ($chars / 3));
        $text = mb_substr($body, $start, $chars);
        $out = self::highlight($text, $needles);
        return ($start > 0 ? '…' : '') . $out . (mb_strlen($body) > $start + $chars ? '…' : '');
    }

    /** Like stripMarks, but each mark becomes a space so character offsets stay put. */
    private static function stripMarksKeepLength(string $text): string
    {
        return (string) preg_replace('/[\x{0610}-\x{061A}\x{064B}-\x{065F}\x{0640}\x{0670}\x{06D6}-\x{06ED}]/u', ' ', $text);
    }

    /**
     * Escape the text and wrap every match of the needles in <mark>, longest
     * needle first and without ever nesting one mark inside another.
     */
    private static function highlight(string $text, array $needles): string
    {
        $hay = self::normalize(self::stripMarksKeepLength($text));
        $len = mb_strlen($text);
        $taken = array_fill(0, max($len, 1), false);
        $spans = [];
        foreach ($needles as $needle) {
            $nlen = mb_strlen($needle);
            if ($nlen === 0) {
                continue;
            }
            $from = 0;
            while (($pos = mb_strpos($hay, $needle, $from)) !== false) {
                $free = true;
                for ($i = $pos; $i < $pos + $nlen; $i++) {
                    if ($taken[$i] ?? false) {
                        $free = false;
                        break;
                    }
                }
                if ($free) {
                    for ($i = $pos; $i < $pos + $nlen; $i++) {
                        $taken[$i] = true;
                    }
                    $spans[$pos] = $nlen;
                }
                $from = $pos + $nlen;
            }
        }
        ksort($spans);
        $out = '';
        $cursor = 0;
        foreach ($spans as $pos => $nlen) {
            $out .= htmlspecialchars(mb_substr($text, $cursor, $pos - $cursor), ENT_QUOTES, 'UTF-8')
                 . '<mark>' . htmlspecialchars(mb_substr($text, $pos, $nlen), ENT_QUOTES, 'UTF-8') . '</mark>';
            $cursor = $pos + $nlen;
        }
        return $out . htmlspecialchars(mb_substr($text, $cursor), ENT_QUOTES, 'UTF-8');
    }

}
