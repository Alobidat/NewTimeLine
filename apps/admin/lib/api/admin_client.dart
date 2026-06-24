/// Thin HTTP client for the Chronos Admin API (/admin/*).
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import 'models.dart';

class ApiException implements Exception {
  ApiException(this.message);
  final String message;
  @override
  String toString() => 'ApiException: $message';
}

class AdminClient {
  AdminClient({String? baseUrl, String? token, http.Client? client})
    : baseUrl = baseUrl ?? AdminConfig.apiBaseUrl,
      token = token ?? AdminConfig.adminToken,
      _http = client ?? http.Client();

  final String baseUrl;
  final String token;
  final http.Client _http;

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (token.isNotEmpty) 'Authorization': 'Bearer $token',
  };

  Never _fail(Uri uri, http.Response resp) {
    final detail = resp.body.isNotEmpty ? ' — ${resp.body}' : '';
    throw ApiException('${uri.path} → ${resp.statusCode}$detail');
  }

  Future<dynamic> _get(String path, [Map<String, String>? query]) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);
    final resp = await _http.get(uri, headers: _headers);
    if (resp.statusCode != 200) _fail(uri, resp);
    return jsonDecode(resp.body);
  }

  Future<OverviewView> overview() async =>
      OverviewView.fromJson(await _get('/admin/overview') as Map<String, dynamic>);

  Future<List<ComponentView>> components({String? kind}) async {
    final list = await _get('/admin/components', {'kind': ?kind}) as List;
    return list.map((e) => ComponentView.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<ComponentDetail> component(String id) async =>
      ComponentDetail.fromJson(await _get('/admin/components/$id') as Map<String, dynamic>);

  Future<List<ConfigEntry>> config({String? scope, String? component}) async {
    final list = await _get('/admin/config', {
      'scope': ?scope,
      'component': ?component,
    }) as List;
    return list.map((e) => ConfigEntry.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<RunView>> runs({String? component, int limit = 50}) async {
    final list = await _get('/admin/runs', {
      'component': ?component,
      'limit': limit.toString(),
    }) as List;
    return list.map((e) => RunView.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<StorageView> storage() async =>
      StorageView.fromJson(await _get('/admin/storage') as Map<String, dynamic>);

  Future<SystemView> system() async =>
      SystemView.fromJson(await _get('/admin/system') as Map<String, dynamic>);

  /// Run a declared component action (e.g. enable/disable). Returns the response body.
  Future<Map<String, dynamic>> action(String componentId, String action) async {
    final uri = Uri.parse('$baseUrl/admin/components/$componentId/actions/$action');
    final resp = await _http.post(uri, headers: _headers);
    if (resp.statusCode != 200) _fail(uri, resp);
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  // ── AI users (bots) ──────────────────────────────────────────────────────────────────
  Future<BotRoster> bots({int limit = 200}) async => BotRoster.fromJson(
    await _get('/admin/bots', {'limit': limit.toString()}) as Map<String, dynamic>,
  );

  Future<BotDetail> bot(String id) async =>
      BotDetail.fromJson(await _get('/admin/bots/$id') as Map<String, dynamic>);

  Future<BotView> updateBot(String id, Map<String, dynamic> patch) async {
    final uri = Uri.parse('$baseUrl/admin/bots/$id');
    final resp = await _http.patch(uri, headers: _headers, body: jsonEncode(patch));
    if (resp.statusCode != 200) _fail(uri, resp);
    return BotView.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
  }

  /// Enqueue a one-off post/interact job for a bot, or bootstrap/retract. Returns the body.
  Future<Map<String, dynamic>> _post(String path, [Object? body]) async {
    final uri = Uri.parse('$baseUrl$path');
    final resp = await _http.post(uri, headers: _headers, body: body == null ? null : jsonEncode(body));
    if (resp.statusCode != 200) _fail(uri, resp);
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  Future<void> botAction(String id, String action) => _post('/admin/bots/$id/actions/$action');

  Future<void> retractPost(String eventId) => _post('/admin/bots/posts/$eventId/retract');

  Future<void> bootstrapBots(int count, int postsPerBot) =>
      _post('/admin/bots/bootstrap', {'count': count, 'posts_per_bot': postsPerBot});

  /// Update a config key (validated server-side against its spec). Returns the updated entry.
  Future<ConfigEntry> setConfig(String key, dynamic value) async {
    final uri = Uri.parse('$baseUrl/admin/config/$key');
    final resp = await _http.put(uri, headers: _headers, body: jsonEncode({'value': value}));
    if (resp.statusCode != 200) _fail(uri, resp);
    return ConfigEntry.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
  }

  void close() => _http.close();
}
