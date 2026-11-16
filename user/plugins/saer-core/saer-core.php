<?php
namespace Grav\Plugin;

use Grav\Common\Plugin;
use Grav\Plugin\SaerCore\Core;
use Grav\Plugin\SaerCore\StatsController;
use RocketTheme\Toolbox\Event\Event;

/**
 * saer-core: downloads through /dl/{id} with an optional/required form, and cookie-free
 * statistics (page views, downloads, who downloaded) shown in Admin2.
 */
class SaerCorePlugin extends Plugin
{
    private ?array $dl = null;
    private $viewPage = null;

    public static function getSubscribedEvents(): array
    {
        return [
            'onPluginsInitialized' => [['autoload', 100000], ['onPluginsInitialized', 0]],
            'onApiRegisterRoutes' => ['onApiRegisterRoutes', 0],
            'onApiSidebarItems' => ['onApiSidebarItems', 0],
            'onApiPluginPageInfo' => ['onApiPluginPageInfo', 0],
            'onApiDashboardWidgets' => ['onApiDashboardWidgets', 0],
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
        $routes->get('/saer-core/diag', [StatsController::class, 'diag']);
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
