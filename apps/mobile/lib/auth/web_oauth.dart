/// Web OAuth redirect helpers (Phase 4-G follow-up): on the web the sign-in handoff is a
/// real full-page redirect to the provider and back, with the PKCE verifier/state stashed in
/// `sessionStorage` so they survive the round-trip. Off the web these are no-ops and callers
/// fall back to the manual paste flow in `oauth_flow.dart`.
///
/// Mirrors the `web_video` conditional-import split so the `package:web` calls only compile on
/// the web target.
library;

export 'web_oauth_stub.dart' if (dart.library.js_interop) 'web_oauth_web.dart';
