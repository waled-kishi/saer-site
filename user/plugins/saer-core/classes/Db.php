<?php
namespace Grav\Plugin\SaerCore;

use PDO;

/**
 * SQLite storage for saer-core (user/data/saer-core/saer.sqlite).
 *
 * Tables
 *   files      one row per downloadable file: the stable id behind /dl/{id}
 *   profiles   what a visitor typed into the download form (name, age band, country, gender)
 *   downloads  one row per download (linked to a profile when the visitor filled the form)
 *   views      one row per page view (no IP stored; "visitor" is a salted daily hash)
 *   crawlers   daily visitor hashes caught opening pages faster than a person reads (not counted)
 *   registrations  one row per course registration sent from the course page's own form
 *   search_docs / search_fts   the site search index (see Search)
 */
class Db
{
    private static ?PDO $pdo = null;
    private static string $dir = '';

    public static function dir(): string
    {
        return self::$dir;
    }

    public static function pdo(string $dir): PDO
    {
        if (self::$pdo) {
            return self::$pdo;
        }
        if (!is_dir($dir)) {
            @mkdir($dir, 0775, true);
        }
        self::$dir = $dir;
        $pdo = new PDO('sqlite:' . $dir . '/saer.sqlite', null, null, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
        $pdo->exec('PRAGMA busy_timeout = 5000');
        $pdo->exec('PRAGMA journal_mode = WAL');
        $pdo->exec('PRAGMA synchronous = NORMAL');
        self::migrate($pdo);
        return self::$pdo = $pdo;
    }

    private static function migrate(PDO $pdo): void
    {
        $version = (int) $pdo->query('PRAGMA user_version')->fetchColumn();
        if ($version < 1) {
            $pdo->exec(<<<SQL
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY,
                    route TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    label TEXT,
                    created INTEGER NOT NULL,
                    UNIQUE(route, filename)
                );
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY,
                    token TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    age TEXT NOT NULL,
                    country TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    geo TEXT,
                    visitor TEXT,
                    created INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY,
                    file_id INTEGER NOT NULL,
                    route TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    profile_id INTEGER,
                    day TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    visitor TEXT,
                    geo TEXT,
                    device TEXT,
                    ref TEXT
                );
                CREATE INDEX IF NOT EXISTS downloads_day ON downloads(day);
                CREATE INDEX IF NOT EXISTS downloads_file ON downloads(file_id);
                CREATE TABLE IF NOT EXISTS views (
                    id INTEGER PRIMARY KEY,
                    day TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    route TEXT NOT NULL,
                    title TEXT,
                    template TEXT,
                    visitor TEXT,
                    geo TEXT,
                    device TEXT,
                    ref TEXT
                );
                CREATE INDEX IF NOT EXISTS views_day ON views(day);
                CREATE INDEX IF NOT EXISTS views_route ON views(route);
                PRAGMA user_version = 1;
            SQL);
        }
        if ($version < 2) {
            $pdo->exec(<<<SQL
                CREATE TABLE IF NOT EXISTS crawlers (
                    visitor TEXT PRIMARY KEY,
                    day TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    views INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS views_visitor_ts ON views(visitor, ts);
                PRAGMA user_version = 2;
            SQL);
        }
        if ($version < 3) {
            Search::migrate($pdo);
            $pdo->exec('PRAGMA user_version = 3');
        }
        if ($version < 5 && $version >= 4) {
            $pdo->exec('ALTER TABLE registrations ADD COLUMN offer TEXT');
            $pdo->exec('PRAGMA user_version = 5');
        }
        if ($version < 4) {
            // One row per registration. Every answer but the name is optional, because each
            // course decides which fields its form shows.
            $pdo->exec(<<<SQL
                CREATE TABLE IF NOT EXISTS registrations (
                    id INTEGER PRIMARY KEY,
                    route TEXT NOT NULL,
                    course TEXT,
                    name TEXT NOT NULL,
                    whatsapp TEXT,
                    email TEXT,
                    age TEXT,
                    country TEXT,
                    city TEXT,
                    gender TEXT,
                    qualification TEXT,
                    note TEXT,
                    offer TEXT,
                    day TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    visitor TEXT,
                    geo TEXT,
                    device TEXT,
                    ref TEXT
                );
                CREATE INDEX IF NOT EXISTS registrations_route ON registrations(route);
                CREATE INDEX IF NOT EXISTS registrations_day ON registrations(day);
                CREATE INDEX IF NOT EXISTS registrations_visitor ON registrations(route, visitor);
                PRAGMA user_version = 5;
            SQL);
        }
    }
}
