<?php
namespace Grav\Theme;

use Grav\Common\Theme;
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

    /** Pad a number to two digits (01, 02 …) for episode numbering. */
    public function arabicDigits($value): string
    {
        return str_pad((string) (int) $value, 2, '0', STR_PAD_LEFT);
    }
}
