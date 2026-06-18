/// App configuration.
///
/// Override the API base URL at build/run time, e.g.:
///   flutter run --dart-define=API_BASE_URL=http://192.168.2.45:8000
class AppConfig {
  AppConfig._();

  /// Base URL of the Chronos Event API. Defaults to the on-site dev LXC.
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://192.168.2.45:8000',
  );
}
