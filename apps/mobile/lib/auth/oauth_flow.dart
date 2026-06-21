/// The OAuth2/OIDC auth-code+PKCE handoff (Phase 4-G, ADR-0026), isolated from the login
/// UI so the platform differences live in one place.
///
/// CONTRACT: [runOAuthFlow] returns an [AuthSession] on success, `null` if the user
/// cancelled, and throws [ApiException] (or similar) on failure.
///
/// DEPENDENCY LIMITATION: opening an external browser needs `url_launcher`, which is **not**
/// in `pubspec.yaml`. To stay within the existing deps we use a manual fallback that works
/// on **every** platform without adding a dep:
///   1. Fetch the authorize URL + PKCE/state from the backend.
///   2. Show a dialog with the URL (selectable/copyable) for the user to open in a browser.
///   3. The user pastes back the `code` (and `state`) from the redirect.
///   4. We exchange them at `/auth/{provider}/callback` for the session JWT.
/// This is intentionally low-tech but verifiable. TODO(deps): add `url_launcher` (browser
/// launch) and, on web, capture the redirect query params automatically instead of the
/// paste step — both are drop-in replacements for [_promptForCode].
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart';
import '../api/models.dart';

/// A hook so callers (and tests) drive how the redirect code is captured: given the
/// [LoginChallenge], return the `{code, state}` the redirect produced (or null to cancel).
typedef CodePrompter = Future<({String code, String? state})?> Function(
  LoginChallenge challenge,
);

/// Run the sign-in handoff for [provider]. The login screen passes a [prompter] built from
/// its [BuildContext] ([buildContextPrompter]); tests pass a stub. Returns the session on
/// success, null on cancel.
Future<AuthSession?> runOAuthFlow(
  ApiClient api,
  String provider, {
  required CodePrompter prompter,
}) async {
  final challenge = await api.loginChallenge(provider);
  final result = await prompter(challenge);
  if (result == null) return null; // cancelled
  return api.authCallback(
    provider,
    code: result.code,
    state: result.state ?? challenge.state,
    codeVerifier: challenge.codeVerifier,
  );
}

/// The default copy-the-URL / paste-the-code prompter, bound to a live [context].
CodePrompter buildContextPrompter(BuildContext context) =>
    (challenge) => _promptForCode(context, challenge);

/// The default UI prompter: show the authorize URL to copy/open, collect the redirect code.
Future<({String code, String? state})?> _promptForCode(
  BuildContext context,
  LoginChallenge challenge,
) {
  final codeCtl = TextEditingController();
  final stateCtl = TextEditingController(text: challenge.state ?? '');
  return showDialog<({String code, String? state})?>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Authorize in your browser'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '1. Open this URL in a browser and authorize.\n'
              '2. Copy the "code" from the redirect and paste it below.',
            ),
            const SizedBox(height: 12),
            SelectableText(
              challenge.authorizeUrl,
              style: const TextStyle(fontSize: 12),
            ),
            const SizedBox(height: 4),
            TextButton.icon(
              onPressed: () => Clipboard.setData(
                ClipboardData(text: challenge.authorizeUrl),
              ),
              icon: const Icon(Icons.copy, size: 16),
              label: const Text('Copy URL'),
            ),
            const SizedBox(height: 12),
            TextField(
              key: const Key('oauth-code-field'),
              controller: codeCtl,
              decoration: const InputDecoration(labelText: 'Authorization code'),
            ),
            TextField(
              controller: stateCtl,
              decoration: const InputDecoration(labelText: 'State (if shown)'),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(null),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            final code = codeCtl.text.trim();
            if (code.isEmpty) return;
            Navigator.of(ctx).pop((
              code: code,
              state: stateCtl.text.trim().isEmpty ? null : stateCtl.text.trim(),
            ));
          },
          child: const Text('Finish sign-in'),
        ),
      ],
    ),
  );
}
