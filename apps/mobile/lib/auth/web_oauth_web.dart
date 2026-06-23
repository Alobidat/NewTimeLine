/// Web implementation of the OAuth redirect flow. The verifier/state/redirect_uri are stashed
/// in `sessionStorage` (survives the full-page redirect within the same tab), the page is sent
/// to the provider's authorize URL, and on return [capturePendingOAuth] reads `?code&state`
/// from the URL and pairs them with the stash. [clearPendingOAuth] then strips the query so a
/// reload can't re-process the code.
library;

import 'package:web/web.dart' as web;

/// A captured provider redirect (code + the stashed PKCE material) ready to exchange.
class PendingOAuth {
  const PendingOAuth({
    required this.provider,
    required this.code,
    required this.state,
    required this.codeVerifier,
    required this.redirectUri,
  });
  final String provider;
  final String code;
  final String state;
  final String codeVerifier;
  final String redirectUri;
}

bool get isWebPlatform => true;

/// The app origin with a trailing slash — what the provider redirects back to. This exact
/// string must be registered as an Authorized redirect URI in the provider's console.
String webRedirectUri() => '${web.window.location.origin}/';

const _kKey = 'nt_oauth';

void stashOAuth({
  required String provider,
  required String state,
  required String codeVerifier,
  required String redirectUri,
}) {
  // Newline-joined (none of the values contain newlines): provider, state, verifier, uri.
  web.window.sessionStorage
      .setItem(_kKey, '$provider\n$state\n$codeVerifier\n$redirectUri');
}

void redirectToAuthorize(String url) => web.window.location.assign(url);

PendingOAuth? capturePendingOAuth() {
  final params = Uri.parse(web.window.location.href).queryParameters;
  final code = params['code'];
  final state = params['state'];
  if (code == null || state == null) return null;
  final raw = web.window.sessionStorage.getItem(_kKey);
  if (raw == null) return null;
  final parts = raw.split('\n');
  if (parts.length < 4) return null;
  if (parts[1] != state) return null; // state mismatch → ignore (CSRF guard)
  return PendingOAuth(
    provider: parts[0],
    code: code,
    state: state,
    codeVerifier: parts[2],
    redirectUri: parts[3],
  );
}

void clearPendingOAuth() {
  web.window.sessionStorage.removeItem(_kKey);
  // Drop ?code&state from the address bar so a refresh doesn't replay the exchange.
  final loc = web.window.location;
  web.window.history.replaceState(null, '', '${loc.origin}${loc.pathname}');
}
