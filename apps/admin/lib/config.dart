/// Admin Portal configuration.
///
/// Override at build/run time, e.g.:
///   flutter run --dart-define=API_BASE_URL=http://192.168.2.45:8000 \
///               --dart-define=ADMIN_TOKEN=secret
class AdminConfig {
  AdminConfig._();

  /// Base URL of the Chronos API (the Admin API lives under /admin). Defaults to dev LXC.
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://192.168.2.45:8000',
  );

  /// Bearer token for the Admin API. Empty is allowed only when the API runs open in dev.
  static const String adminToken = String.fromEnvironment('ADMIN_TOKEN', defaultValue: '');

  /// How often live screens re-poll the API (no realtime gateway yet — ADR-0019).
  static const Duration pollInterval = Duration(seconds: 5);
}
