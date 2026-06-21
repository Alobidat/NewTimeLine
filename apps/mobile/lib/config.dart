import 'package:flutter/foundation.dart' show kIsWeb;

/// App configuration.
///
/// Override the API base URL at build/run time, e.g.:
///   flutter run --dart-define=API_BASE_URL=http://192.168.2.45:8000
class AppConfig {
  AppConfig._();

  /// Explicit override (always wins when set).
  static const String _override =
      String.fromEnvironment('API_BASE_URL', defaultValue: '');

  /// Base URL of the Chronos Event API.
  ///
  /// - An explicit `--dart-define=API_BASE_URL=…` always wins.
  /// - On the **web**, default to a same-origin `/api` path that the serving nginx
  ///   reverse-proxies to the API container. This means the app works from *any* host,
  ///   port, or tunnel that can reach the web origin — no hardcoded API IP, and no CORS —
  ///   which fixes "Failed to fetch `http://lan-ip:8000/…`" when the browser can't route to
  ///   the API's LAN address directly.
  /// - On native builds (no same-origin server), default to the on-site dev LXC.
  static String get apiBaseUrl {
    if (_override.isNotEmpty) return _override;
    return kIsWeb ? '/api' : 'http://192.168.2.45:8000';
  }

  /// Public web origin used to build shareable deep links (`<origin>/?event=<id>`).
  ///
  /// - An explicit `--dart-define=SHARE_BASE_URL=https://…` always wins.
  /// - On the **web**, default to the current origin (`Uri.base.origin`) so a shared link
  ///   always points back at the very deployment the user is on — no hardcoded domain.
  /// - On native builds there is no origin; without an override we return empty and callers
  ///   degrade to sharing the bare event id / title.
  static String get shareBaseUrl {
    const override = String.fromEnvironment('SHARE_BASE_URL', defaultValue: '');
    if (override.isNotEmpty) return override;
    return kIsWeb ? Uri.base.origin : '';
  }
}
