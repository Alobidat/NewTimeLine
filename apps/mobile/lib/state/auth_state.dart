/// The app's session/auth state (Phase 4-G, ADR-0026): holds the session JWT + current
/// [SessionUser], drives the [ApiClient] Bearer, and tracks the two interaction gates —
/// **agreement acceptance** and **email verification**. A [ChangeNotifier] so the account
/// entry point + any gate UI rebuild on sign-in / sign-out.
///
/// PERSISTENCE: `shared_preferences` is **not** in `pubspec.yaml`, so the session is kept
/// **in memory** for now (lost on app restart). A pluggable [SessionStore] is provided so
/// persistence is a one-class swap once the dep is added — see [InMemorySessionStore] and
/// the README. TODO(deps): add `shared_preferences`, implement a `PrefsSessionStore`, and
/// pass it to [AuthState] so the JWT survives launches.
library;

import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/models.dart';

/// Abstraction over where the session JWT (+ a minimal user snapshot) is persisted.
abstract class SessionStore {
  Future<String?> readToken();
  Future<Map<String, dynamic>?> readUser();
  Future<void> write(String token, Map<String, dynamic>? user);
  Future<void> clear();
}

/// Default store: keeps the session in process memory only (no cross-launch persistence).
/// Swap for a `shared_preferences`-backed store once the dep is available.
class InMemorySessionStore implements SessionStore {
  String? _token;
  Map<String, dynamic>? _user;

  @override
  Future<String?> readToken() async => _token;

  @override
  Future<Map<String, dynamic>?> readUser() async => _user;

  @override
  Future<void> write(String token, Map<String, dynamic>? user) async {
    _token = token;
    _user = user;
  }

  @override
  Future<void> clear() async {
    _token = null;
    _user = null;
  }
}

class AuthState extends ChangeNotifier {
  AuthState({required this.api, SessionStore? store})
    : _store = store ?? InMemorySessionStore();

  final ApiClient api;
  final SessionStore _store;

  String? _token;
  SessionUser? _user;
  bool _agreementAccepted = false;
  bool _loaded = false;

  /// True once [load] has run (so the UI knows whether to wait before gating).
  bool get loaded => _loaded;

  /// True when a session JWT is held.
  bool get isSignedIn => _token != null;

  SessionUser? get user => _user;

  /// Email verified (provider asserted it, or the user confirmed a code). Required to interact.
  bool get emailVerified => _user?.emailVerified ?? false;

  /// Current agreement accepted. Required to interact; re-checked on each sign-in.
  bool get agreementAccepted => _agreementAccepted;

  /// The single gate the rest of the app cares about: a signed-in, verified, consented user
  /// may interact (react/comment/promote/upload/follow). Reads are always allowed.
  bool get canInteract => isSignedIn && emailVerified && _agreementAccepted;

  /// Restore any persisted session on startup and attach the Bearer. Safe to call once at
  /// app boot; refreshes [user] + agreement status from the server when a token is present.
  Future<void> load() async {
    final token = await _store.readToken();
    if (token != null) {
      _token = token;
      api.sessionToken = token;
      final cached = await _store.readUser();
      if (cached != null) _user = SessionUser.fromJson(cached);
      // Best-effort refresh; keep the cached session if the network is down.
      try {
        await refresh();
      } catch (_) {/* offline / transient — keep cached session */}
    }
    _loaded = true;
    notifyListeners();
  }

  /// Adopt a freshly-minted session (from the OAuth callback): store the JWT, attach the
  /// Bearer, set the user, then refresh the interaction gates.
  Future<void> adopt(AuthSession session) async {
    _token = session.token;
    _user = session.user;
    api.sessionToken = session.token;
    await _store.write(session.token, session.user?.toJson());
    notifyListeners();
    try {
      await refresh();
    } catch (_) {/* gates default closed until a successful refresh */}
  }

  /// Re-fetch the current user + agreement status from the server (after sign-in, verify,
  /// or consent). Updates [canInteract].
  Future<void> refresh() async {
    if (!isSignedIn) return;
    _user = await api.me();
    await _store.write(_token!, _user?.toJson());
    try {
      _agreementAccepted = (await api.agreementStatus()).accepted;
    } catch (_) {
      _agreementAccepted = false;
    }
    notifyListeners();
  }

  /// Mark consent locally after a successful accept (avoids an extra round-trip).
  void markAgreementAccepted() {
    _agreementAccepted = true;
    notifyListeners();
  }

  /// Clear the session everywhere (sign-out or post-deletion).
  Future<void> signOut() async {
    _token = null;
    _user = null;
    _agreementAccepted = false;
    api.sessionToken = null;
    await _store.clear();
    notifyListeners();
  }
}
