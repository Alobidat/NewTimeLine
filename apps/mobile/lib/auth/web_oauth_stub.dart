/// Off-web stub for the web OAuth redirect flow: every operation is a no-op and there is
/// never a pending redirect, so native callers transparently fall back to the paste flow.
library;

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

/// True only on the web target.
bool get isWebPlatform => false;

/// The app-origin redirect URI the provider returns to (web only).
String webRedirectUri() => '';

void stashOAuth({
  required String provider,
  required String state,
  required String codeVerifier,
  required String redirectUri,
}) {}

void redirectToAuthorize(String url) {}

PendingOAuth? capturePendingOAuth() => null;

void clearPendingOAuth() {}
