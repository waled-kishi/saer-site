<?php
namespace Grav\Theme;

use Grav\Common\Data\Blueprint;
use Grav\Common\Grav;
use Grav\Common\Theme;
use Twig\TwigFunction;
use Twig\TwigFilter;

/**
 * Theme for the Sheikh Mohammed Saer Al-Shabaan website.
 * Adds a few Twig helpers the templates rely on.
 */
class Saer extends Theme
{
    public static function getSubscribedEvents(): array
    {
        return [
            'onTwigInitialized' => ['onTwigInitialized', 0],
        ];
    }

    public function onTwigInitialized(): void
    {
        $twig = $this->grav['twig']->twig();
        $twig->addFilter(new TwigFilter('yt_id', [$this, 'youtubeId']));
        $twig->addFilter(new TwigFilter('yt_list', [$this, 'youtubeList']));
        $twig->addFilter(new TwigFilter('ar_digits', [$this, 'arabicDigits']));
        $twig->addFilter(new TwigFilter('asset_v', [$this, 'assetVersion']));
        $twig->addFunction(new TwigFunction('media_pick', [$this, 'mediaPick']));
        $twig->addFunction(new TwigFunction('book_files', [$this, 'bookFiles']));
        $twig->addFunction(new TwigFunction('book_cover', [$this, 'bookCover']));
        $twig->addFunction(new TwigFunction('item_words', [$this, 'itemWords']));
        $twig->addFunction(new TwigFunction('ar_count', [self::class, 'arCount']));
    }

    /** Extract a YouTube video id from a URL or return the input if it already is an id. */
    public function youtubeId(?string $value): string
    {
        $value = trim((string) $value);
        if ($value === '') {
            return '';
        }
        if (preg_match('~(?:youtu\.be/|v=|embed/|shorts/|live/)([A-Za-z0-9_-]{11})~', $value, $m)) {
            return $m[1];
        }
        return preg_match('~^[A-Za-z0-9_-]{11}$~', $value) ? $value : '';
    }

    /** Extract a YouTube playlist id from a URL or return the input if it already is one. */
    public function youtubeList(?string $value): string
    {
        $value = trim((string) $value);
        if (preg_match('~[?&]list=([A-Za-z0-9_-]+)~', $value, $m)) {
            return $m[1];
        }
        return preg_match('~^[A-Za-z0-9_-]{10,}$~', $value) ? $value : '';
    }

    /** Append ?v=<file modification time> to a theme asset so browsers fetch new versions after a deploy. */
    public function assetVersion(string $stream): string
    {
        $locator = $this->grav['locator'];
        $file = $locator->findResource($stream, true);
        return $stream . ($file && is_file($file) ? '?v=' . filemtime($file) : '');
    }

    /** Pad a number to two digits (01, 02 …) for episode numbering. */
    public function arabicDigits($value): string
    {
        return str_pad((string) (int) $value, 2, '0', STR_PAD_LEFT);
    }

    /**
     * Resolve the value of a `media` field (one item or several) to files.
     * Accepts a filename from the page media, a site/URL path, or the
     * {value|url|filename: …} shapes the admin may store. Missing files are skipped.
     * Returns [{medium|null, url, name, ext, size}].
     */
    public function mediaPick($page, $value): array
    {
        $out = [];
        if ($value === null || $value === '' || $value === []) {
            return $out;
        }
        if (is_array($value)) {
            foreach (['value', 'url', 'filename', 'name', 'path'] as $k) {
                if (isset($value[$k]) && is_string($value[$k])) {
                    return $this->mediaPick($page, $value[$k]);
                }
            }
            foreach ($value as $v) {
                foreach ($this->mediaPick($page, $v) as $item) {
                    $out[] = $item;
                }
            }
            return $out;
        }
        $value = trim((string) $value);
        if ($value === '') {
            return $out;
        }
        $media = $page ? $page->media()->all() : [];
        $base = basename(parse_url($value, PHP_URL_PATH) ?: $value);
        if (!preg_match('~^(https?:)?//~i', $value) && isset($media[$base])) {
            $m = $media[$base];
            $out[] = ['medium' => $m, 'url' => $m->url(), 'name' => $base,
                      'ext' => strtolower(pathinfo($base, PATHINFO_EXTENSION)), 'size' => (int) ($m->get('size') ?: 0)];
        } elseif (preg_match('~^(https?://|/)~i', $value)) {
            $out[] = ['medium' => null, 'url' => $value, 'name' => $base,
                      'ext' => strtolower(pathinfo($base, PATHINFO_EXTENSION)), 'size' => 0];
        }
        return $out;
    }

    /**
     * Words for the items of a series: episode (حلقة), lesson (درس), khutba (خطبة), lecture (محاضرة).
     * Taken from header.item_word on the page or its nearest ancestor; pages under /lectures
     * default to lesson, everything else to episode.
     */
    public function itemWords($page, $n = null): array
    {
        $words = [
            'episode' => ['حلقة', 'حلقات', 'الحلقة', 'الحلقة الأولى', 'تقديم: أ. سائر', 'حلقتان'],
            'lesson'  => ['درس', 'دروس', 'الدرس', 'الدرس الأول', 'الشيخ محمد سائر الشبعان', 'درسان'],
            'khutba'  => ['خطبة', 'خطب', 'الخطبة', 'الخطبة الأولى', 'الشيخ محمد سائر الشبعان', 'خطبتان'],
            'lecture' => ['محاضرة', 'محاضرات', 'المحاضرة', 'المحاضرة الأولى', 'الشيخ محمد سائر الشبعان', 'محاضرتان'],
        ];
        $key = null;
        for ($p = $page; $p && !$key; $p = $p->parent()) {
            $w = $p->header()->item_word ?? null;
            if (is_string($w) && isset($words[$w])) {
                $key = $w;
            }
            if ($p->root() ?? false) {
                break;
            }
        }
        if (!$key) {
            $key = ($page && str_starts_with((string) $page->route(), '/lectures')) ? 'lesson' : 'episode';
        }
        [$one, $many, $the, $first, $by, $two] = $words[$key];
        $out = ['key' => $key, 'one' => $one, 'many' => $many, 'the' => $the, 'first' => $first, 'by' => $by, 'all' => 'ال' . $many];
        if ($n !== null) {
            $n = (int) $n;
            $out['count'] = self::arCount($n, $one, $two, $many);
        }
        return $out;
    }

    /** Arabic count phrase: 1 → "خطبة واحدة"-style single, 2 → dual, 3–10 → plural, else singular. */
    public static function arCount($n, string $one, string $two, string $many): string
    {
        $n = (int) $n;
        if ($n === 1) {
            return '1 ' . $one;
        }
        if ($n === 2) {
            return $two;
        }
        return $n . ' ' . (($n >= 3 && $n <= 10) ? $many : $one);
    }

    /** The download files chosen in a book's "files" list, each with its button label. */
    public function bookFiles($page): array
    {
        $rows = $page ? ($page->header()->files ?? []) : [];
        $out = [];
        foreach ((array) $rows as $row) {
            $row = (array) $row;
            $picked = $this->mediaPick($page, $row['file'] ?? null);
            foreach ($picked as $f) {
                $label = trim((string) ($row['label'] ?? ''));
                $f['label'] = $label !== '' ? $label : (count($picked) > 1 ? $f['name'] : '');
                $out[] = $f;
            }
        }
        foreach ($out as $i => $f) {
            if ($f['label'] === '') {
                $out[$i]['label'] = count($out) > 1 ? $f['name'] : 'تحميل الكتاب';
            }
            // Count downloads: page files go through saer-core's /dl/{id} when the plugin is on.
            if ($f['medium'] && isset($this->grav['saer_core'])) {
                try {
                    $id = $this->grav['saer_core']->fileId((string) $page->route(), $f['name'], $out[$i]['label']);
                    $out[$i]['url'] = rtrim((string) $this->grav['base_url'], '/') . '/dl/' . $id;
                } catch (\Throwable $e) {
                    // keep the direct link
                }
            }
        }
        return $out;
    }

    /** The cover chosen in a book's "cover" field, or null. */
    public function bookCover($page): ?array
    {
        return $page ? ($this->mediaPick($page, $page->header()->cover ?? null)[0] ?? null) : null;
    }

    /** Options for "related programme/series" selects: '' (none) + every series under /programs. */
    public static function seriesOptions(): array
    {
        return ['' => '— بدون ربط —'] + self::pageOptions('/programs', 'series');
    }

    /** Options for "linked book" selects: '' (none) + every book under /books. */
    public static function bookOptions(): array
    {
        return ['' => '— بدون ربط —'] + self::pageOptions('/books', 'book');
    }

    private static function pageOptions(string $root, string $template): array
    {
        $pages = Grav::instance()['pages'];
        if (method_exists($pages, 'enablePages')) {
            $pages->enablePages();
        }
        $opts = [];
        $walk = function ($page, int $depth) use (&$walk, &$opts, $template) {
            foreach ($page->children() as $child) {
                if ($child->template() === $template) {
                    $opts[$child->route()] = str_repeat('— ', $depth) . $child->title();
                    $walk($child, $depth + 1);
                }
            }
        };
        $start = $pages->find($root);
        if ($start) {
            $walk($start, 0);
        }
        return $opts;
    }
}

// Let blueprints call the option providers above (Grav refuses unlisted data-options@ callables).
if (method_exists(Blueprint::class, 'addAllowedDynamicCallable')) {
    Blueprint::addAllowedDynamicCallable('Grav\Theme\Saer::seriesOptions');
    Blueprint::addAllowedDynamicCallable('Grav\Theme\Saer::bookOptions');
}
