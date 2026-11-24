<?php
namespace Grav\Plugin;

use Grav\Common\Plugin;
use Grav\Plugin\SaerCore\Core;
use Grav\Plugin\SaerCore\Search;
use Grav\Plugin\SaerCore\StatsController;
use RocketTheme\Toolbox\Event\Event;

/**
 * saer-core: downloads through /dl/{id} with an optional/required form, and cookie-free
 * statistics (page views, downloads, who downloaded) shown in Admin2.
 */
class SaerCorePlugin extends Plugin
{
    private ?array $dl = null;
    /** Registration form state for a course page: fields, values, errors, state. */
    private ?array $reg = null;
    private $viewPage = null;

    public static function getSubscribedEvents(): array
    {
        return [
            'onPluginsInitialized' => [['autoload', 100000], ['onPluginsInitialized', 0]],
            'onApiRegisterRoutes' => ['onApiRegisterRoutes', 0],
            'onApiSidebarItems' => ['onApiSidebarItems', 0],
            'onApiPluginPageInfo' => ['onApiPluginPageInfo', 0],
            'onApiContextPanels' => ['onApiContextPanels', 0],
            'onApiDashboardWidgets' => ['onApiDashboardWidgets', 0],
            'onApiPageCreated' => ['onApiPageChanged', 0],
            'onApiPageUpdated' => ['onApiPageChanged', 0],
            'onApiPageDeleted' => ['onApiPageRemoved', 0],
        ];
    }

    public function autoload(): void
    {
        spl_autoload_register(static function (string $class): void {
            foreach (['Grav\\Plugin\\SaerCore\\' => __DIR__ . '/classes/', 'MaxMind\\Db\\' => __DIR__ . '/lib/MaxMind/Db/'] as $ns => $dir) {
                if (str_starts_with($class, $ns)) {
                    $file = $dir . str_replace('\\', '/', substr($class, strlen($ns))) . '.php';
                    if (is_file($file)) {
                        require $file;
                    }
                }
            }
        });
        if (!isset($this->grav['saer_core'])) {
            $this->grav['saer_core'] = new Core($this->grav);
        }
    }

    public function onPluginsInitialized(): void
    {
        if ($this->isAdmin()) {
            return;
        }
        $path = '/' . trim((string) $this->grav['uri']->path(), '/');
        if (preg_match('~^/(admin|api|user|assets|images|system|vendor)(/|$)~', $path)) {
            return;
        }
        $this->enable([
            'onTwigTemplatePaths' => ['onTwigTemplatePaths', 0],
            'onPagesInitialized' => ['onPagesInitialized', 1000],
            'onPageInitialized' => ['onPageInitialized', 0],
            'onTwigSiteVariables' => ['onTwigSiteVariables', 0],
            'onOutputGenerated' => ['onOutputGenerated', 0],
            'onShutdown' => ['onShutdown', 0],
        ]);
    }

    public function onTwigTemplatePaths(): void
    {
        $this->grav['twig']->twig_paths[] = __DIR__ . '/templates';
    }

    /* ---------------- downloads ---------------- */

    public function onPagesInitialized(): void
    {
        $path = '/' . trim((string) $this->grav['uri']->path(), '/');
        $ext = strtolower((string) $this->grav['uri']->extension());
        if ($path === '/sitemap.xml' || ($path === '/sitemap' && $ext === 'xml')) {
            $this->sendSitemap();
        }
        if (!preg_match('~^/dl/(\d+)$~', $path, $m)) {
            return;
        }
        /** @var Core $core */
        $core = $this->grav['saer_core'];
        $file = $core->file((int) $m[1]);
        $page = $file ? $this->grav['pages']->find($file['route']) : null;
        $media = $page ? ($page->media()->all()[$file['filename']] ?? null) : null;
        if (!$file || !$page || !$media || !is_file($media->path())) {
            return; // falls through to the normal 404
        }

        $mode = (string) ($page->header()->download_form ?? '');
        if (!in_array($mode, ['off', 'optional', 'required'], true)) {
            $mode = (string) $this->config->get('plugins.saer-core.download_form', 'required');
        }
        $label = (string) ($file['label'] ?: $file['filename']);
        $vars = ['id' => (int) $file['id'], 'book' => $page, 'label' => $label, 'mode' => $mode, 'errors' => [],
                 'values' => [], 'state' => 'form', 'ages' => Core::AGES, 'genders' => Core::GENDERS,
                 'countries' => $core->countries(), 'stamp' => $core->formStamp(),
                 'url' => $this->grav['base_url'] . '/dl/' . (int) $file['id']];

        if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
            $post = $_POST;
            [$values, $errors] = $core->validateForm($post);
            $vars['values'] = $values;
            if (!empty($post['website']) || !$core->stampOk((string) ($post['stamp'] ?? ''))) {
                $errors['form'] = 'تعذّر إرسال النموذج. أعد المحاولة بعد لحظات.';
            } elseif ($core->tooManyForms()) {
                $errors['form'] = 'محاولات كثيرة. حاول لاحقاً.';
            }
            if (!$errors) {
                $core->createProfile($values);
                $vars['state'] = 'thanks';
            } else {
                $vars['errors'] = $errors;
            }
            $this->renderDownloadPage($page, $vars);
            return;
        }

        $profile = $core->profileFromCookie();
        if ($mode === 'off' || $profile || ($mode === 'optional' && isset($_GET['skip']))) {
            if (!$core->isBot() && ($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'GET') {
                try {
                    $core->recordDownload($file, $profile ? (int) $profile['id'] : null);
                } catch (\Throwable $e) {
                    $this->grav['log']->warning('saer-core: download not recorded: ' . $e->getMessage());
                }
            }
            $this->sendFile($media->path(), (string) $file['filename']);
        }
        $this->renderDownloadPage($page, $vars);
    }

    /* ---------------- sitemap ---------------- */

    /**
     * Serves /sitemap.xml: every published, routable page that is not marked
     * "coming soon" (the page itself or any ancestor, which is what the theme
     * turns into a noindex panel).
     */
    private function sendSitemap(): void
    {
        $items = [];
        foreach ($this->grav['pages']->all() as $page) {
            if (!$page || !$page->routable() || !$page->published()) {
                continue;
            }
            if (in_array($page->template(), ['error', 'saer-download', 'search'], true)) {
                continue;
            }
            $soon = false;
            for ($p = $page; $p; $p = $p->parent()) {
                if (($p->header()->coming_soon ?? false)) {
                    $soon = true;
                    break;
                }
            }
            if ($soon) {
                continue;
            }
            $url = (string) $page->canonical(true);
            if ($url === '') {
                continue;
            }
            $items[$url] = (int) $page->modified();
        }
        ksort($items);

        $xml = '<?xml version="1.0" encoding="UTF-8"?>' . "\n"
             . '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' . "\n";
        foreach ($items as $url => $modified) {
            $xml .= '  <url><loc>' . htmlspecialchars($url, ENT_XML1 | ENT_COMPAT, 'UTF-8') . '</loc>'
                 . ($modified ? '<lastmod>' . gmdate('Y-m-d', $modified) . '</lastmod>' : '')
                 . "</url>\n";
        }
        $xml .= '</urlset>' . "\n";

        while (ob_get_level() > 0) {
            ob_end_clean();
        }
        header('Content-Type: application/xml; charset=utf-8');
        header('Content-Length: ' . strlen($xml));
        header('Cache-Control: public, max-age=3600');
        echo $xml;
        exit;
    }

    private function renderDownloadPage($book, array $vars): void
    {
        $p = clone $book;
        $p->template('saer-download');
        unset($this->grav['page']);
        $this->grav['page'] = $p;
        $this->dl = $vars;
    }

    private function sendFile(string $path, string $name): void
    {
        $types = ['pdf' => 'application/pdf', 'epub' => 'application/epub+zip', 'zip' => 'application/zip'];
        $ext = strtolower(pathinfo($name, PATHINFO_EXTENSION));
        while (ob_get_level() > 0) {
            ob_end_clean();
        }
        $ascii = preg_replace('/[^A-Za-z0-9._-]+/', '-', $name) ?: 'download.' . $ext;
        header('Content-Type: ' . ($types[$ext] ?? 'application/octet-stream'));
        header('Content-Disposition: attachment; filename="' . $ascii . '"; filename*=UTF-8\'\'' . rawurlencode($name));
        header('Content-Length: ' . filesize($path));
        header('Cache-Control: private, no-store');
        header('X-Robots-Tag: noindex');
        header('X-Content-Type-Options: nosniff');
        readfile($path);
        exit;
    }

    public function onTwigSiteVariables(): void
    {
        if ($this->dl !== null) {
            $this->grav['twig']->twig_vars['dl'] = $this->dl;
        }
        if ($this->reg !== null) {
            $this->grav['twig']->twig_vars['reg'] = $this->reg;
        }
        $page = $this->grav['page'] ?? null;
        if ($page && $page->template() === 'search') {
            $this->grav['twig']->twig_vars['search'] = $this->runSearch();
        }
    }

    /** Results for the /search page, read from the query string. */
    private function runSearch(): array
    {
        $q = trim((string) ($_GET['q'] ?? ''));
        $q = mb_substr($q, 0, 120);
        $per = 20;
        $page = max(1, (int) ($_GET['page'] ?? 1));
        $out = ['q' => $q, 'page' => $page, 'per' => $per, 'total' => 0, 'results' => [], 'pages' => 0,
                'terms' => Search::terms($q)];
        if ($q === '' || !$out['terms']) {
            return $out;
        }
        try {
            $found = Search::query($this->grav['saer_core']->pdo(), $q, $per, ($page - 1) * $per);
        } catch (\Throwable $e) {
            $this->grav['log']->warning('saer-core: search failed: ' . $e->getMessage());
            return $out + ['error' => true];
        }
        $out['total'] = $found['total'];
        $out['results'] = $found['results'];
        $out['pages'] = (int) ceil($found['total'] / $per);
        return $out;
    }

    /** Keep the index in step with pages saved or created through the admin API. */
    public function onApiPageChanged(Event $event): void
    {
        $page = $event['page'] ?? null;
        if (!$page) {
            return;
        }
        try {
            Search::indexPage($this->grav['saer_core']->pdo(), $page);
        } catch (\Throwable $e) {
            $this->grav['log']->warning('saer-core: search index not updated: ' . $e->getMessage());
        }
    }

    public function onApiPageRemoved(Event $event): void
    {
        $route = (string) ($event['route'] ?? '');
        if ($route === '') {
            return;
        }
        try {
            Search::removeRoute($this->grav['saer_core']->pdo(), $route);
        } catch (\Throwable $e) {
            $this->grav['log']->warning('saer-core: search index not updated: ' . $e->getMessage());
        }
    }

    public function onOutputGenerated(): void
    {
        if ($this->dl !== null && !headers_sent()) {
            header('Cache-Control: private, no-store');
            header('X-Robots-Tag: noindex');
        }
    }

    /* ---------------- page views ---------------- */

    public function onPageInitialized(Event $event): void
    {
        $this->viewPage = $event['page'] ?? null;
        $this->prepareRegistration($this->viewPage);
    }

    /* ---------------- course registration ---------------- */

    /**
     * The registration form of a course page whose register_mode is "internal": renders it,
     * and on POST validates the answers, stores them and shows the thank-you message.
     * Nothing happens on any other page, or once the deadline has passed.
     */
    private function prepareRegistration($page): void
    {
        if (!$page || $page->template() !== 'course') {
            return;
        }
        $h = $page->header();
        if ((string) ($h->register_mode ?? 'external') !== 'internal') {
            return;
        }
        $deadline = (string) ($h->register_deadline ?? '');
        $closed = (string) ($h->status ?? 'soon') !== 'open'
            || ($deadline !== '' && strtotime($deadline . ' 23:59:59') < time());
        /** @var Core $core */
        $core = $this->grav['saer_core'];
        $fields = $core->registrationFields(
            (array) ($h->register_fields ?? ['whatsapp']),
            (array) ($h->register_required ?? ['whatsapp'])
        );
        $vars = ['fields' => $fields, 'values' => [], 'errors' => [], 'state' => $closed ? 'closed' : 'form',
                 'countries' => $core->countries(), 'stamp' => $core->formStamp(),
                 'thanks' => (string) ($h->register_thanks ?? ''), 'intro' => (string) ($h->register_intro ?? '')];

        if (!$closed && ($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST' && isset($_POST['saer_register'])) {
            $post = $_POST;
            [$values, $errors] = $core->validateRegistration($post, $fields);
            $vars['values'] = $values;
            if (!empty($post['website']) || !$core->stampOk((string) ($post['stamp'] ?? ''))) {
                $errors['form'] = 'تعذّر إرسال النموذج. أعد المحاولة بعد لحظات.';
            } elseif ($core->tooManyRegistrations()) {
                $errors['form'] = 'محاولات كثيرة. حاول لاحقاً.';
            } elseif (!$errors && $core->alreadyRegistered($page->route(), $values)) {
                $vars['state'] = 'already';
            }
            if ($vars['state'] !== 'already') {
                if ($errors) {
                    $vars['errors'] = $errors;
                } else {
                    try {
                        $core->createRegistration($page->route(), (string) $page->title(), $values);
                        $vars['state'] = 'thanks';
                        $vars['values'] = [];
                    } catch (\Throwable $e) {
                        $this->grav['log']->warning('saer-core: registration not stored: ' . $e->getMessage());
                        $vars['errors'] = ['form' => 'تعذّر حفظ التسجيل. أعد المحاولة بعد قليل.'];
                    }
                }
            }
        }
        $this->reg = $vars;
    }

    public function onShutdown(): void
    {
        $page = $this->viewPage;
        if (!$page || $this->dl !== null || ($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') {
            return;
        }
        if (http_response_code() !== 200 || $page->template() === 'error') {
            return;
        }
        $purpose = strtolower(($_SERVER['HTTP_SEC_PURPOSE'] ?? '') . ($_SERVER['HTTP_PURPOSE'] ?? '') . ($_SERVER['HTTP_X_MOZ'] ?? ''));
        if (str_contains($purpose, 'prefetch') || str_contains($purpose, 'prerender')) {
            return;
        }
        /** @var Core $core */
        $core = $this->grav['saer_core'];
        if ($core->isBot()) {
            return;
        }
        try {
            $core->recordView((string) ($page->home() ? '/' : $page->route()), (string) $page->title(), (string) $page->template());
        } catch (\Throwable $e) {
            $this->grav['log']->warning('saer-core: view not recorded: ' . $e->getMessage());
        }
    }

    /* ---------------- Admin2 ---------------- */

    public function onApiRegisterRoutes(Event $event): void
    {
        $routes = $event['routes'];
        $routes->get('/saer-core/stats', [StatsController::class, 'stats']);
        $routes->get('/saer-core/summary', [StatsController::class, 'summary']);
        $routes->get('/saer-core/export', [StatsController::class, 'export']);
        $routes->get('/saer-core/files', [StatsController::class, 'files']);
        $routes->get('/saer-core/file', [StatsController::class, 'file']);
        $routes->delete('/saer-core/profiles/{id:\d+}', [StatsController::class, 'deleteProfile']);
        $routes->delete('/saer-core/data', [StatsController::class, 'reset']);
        $routes->get('/saer-core/registrations', [StatsController::class, 'registrations']);
        $routes->delete('/saer-core/registrations/{id:\d+}', [StatsController::class, 'deleteRegistration']);
        $routes->get('/saer-core/search', [StatsController::class, 'searchStatus']);
        $routes->post('/saer-core/search/rebuild', [StatsController::class, 'searchRebuild']);
    }

    public function onApiSidebarItems(Event $event): void
    {
        $items = $event['items'] ?? [];
        $items[] = [
            'id' => 'saer-core-stats',
            'plugin' => 'saer-core',
            'label' => 'الإحصائيات',
            'icon' => 'fa-chart-line',
            'route' => '/plugin/saer-core',
            'priority' => 50,
            'authorize' => 'api.system.read',
        ];
        // Registrations are their own screen inside the same page component (hash route),
        // because a plugin may ship only one admin page.
        $items[] = [
            'id' => 'saer-core-registrations',
            'plugin' => 'saer-core',
            'label' => 'تسجيلات الدورات',
            'icon' => 'fa-user-check',
            'route' => '/plugin/saer-core#registrations',
            'priority' => 51,
            'authorize' => 'api.system.read',
        ];
        $event['items'] = $items;
    }

    public function onApiPluginPageInfo(Event $event): void
    {
        if (($event['plugin'] ?? '') !== 'saer-core') {
            return;
        }
        $event['definition'] = [
            'id' => 'saer-core',
            'plugin' => 'saer-core',
            'title' => 'الإحصائيات',
            'icon' => 'fa-chart-line',
            'page_type' => 'component',
        ];
    }

    /** "ملفات الصفحة" panel in the page editor: download a page's PDF/Word files, even unpublished. */
    public function onApiContextPanels(Event $event): void
    {
        $panels = $event['panels'] ?? [];
        $panels[] = [
            'id' => 'saer-core-files',
            'plugin' => 'saer-core',
            'label' => 'ملفات الصفحة (PDF و Word)',
            'icon' => 'file-down',
            'contexts' => ['pages'],
            'priority' => 20,
            'width' => 460,
            'authorize' => 'api.pages.read',
        ];
        $event['panels'] = $panels;
    }

    public function onApiDashboardWidgets(Event $event): void
    {
        $widgets = $event['widgets'] ?? [];
        $widgets[] = [
            'id' => 'saer-core.summary',
            'label' => 'إحصائيات الموقع',
            'icon' => 'BarChart3',
            'sizes' => ['sm', 'md', 'lg'],
            'defaultSize' => 'md',
            'authorize' => 'api.system.read',
            'priority' => 95,
            'scriptUrl' => '/gpm/plugins/saer-core/widget-script',
        ];
        $event['widgets'] = $widgets;
    }
}
