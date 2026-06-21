/// Sign-in-on-interaction (Phase 4-G, ADR-0026 / social-and-feed §5): the single entry the
/// feed/event overlays call before any write (react/comment/promote/upload/follow). It walks
/// the user through whatever gate is missing — **sign in → accept agreement → verify email**
/// — and returns whether they may now interact, so the caller can resume the pending action.
///
/// USAGE (for IU2 wiring — these files are NOT edited here, see README):
/// ```dart
/// if (await ensureCanInteract(context, api, auth)) {
///   await api.toggleReaction(eventId, 'like'); // the pending action, resumed
/// }
/// ```
/// The pattern is "ask, then resume": [ensureCanInteract] only checks/escalates the gates;
/// the caller owns the action so it stays where the context (event id, comment body) lives.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../state/auth_state.dart';
import 'agreement_screen.dart';
import 'login_screen.dart';
import 'verify_email_screen.dart';

/// Ensure the user can interact, prompting for each missing gate in order. Returns true if
/// the user ends up signed-in + verified + consented (caller resumes its action), false if
/// they cancelled at any step (caller aborts, no error). Reads never call this.
Future<bool> ensureCanInteract(
  BuildContext context,
  ApiClient api,
  AuthState auth,
) async {
  // 1. Sign in.
  if (!auth.isSignedIn) {
    final ok = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => LoginScreen(api: api, auth: auth)),
    );
    if (ok != true || !auth.isSignedIn) return false;
  }

  // 2. Accept the current agreement (re-prompted on version change via refresh()).
  if (!auth.agreementAccepted) {
    if (!context.mounted) return false;
    final ok = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => AgreementScreen(api: api, auth: auth)),
    );
    if (ok != true || !auth.agreementAccepted) return false;
  }

  // 3. Verify email (providers asserting a verified email skip this).
  if (!auth.emailVerified) {
    if (!context.mounted) return false;
    final ok = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => VerifyEmailScreen(api: api, auth: auth)),
    );
    if (ok != true || !auth.emailVerified) return false;
  }

  return auth.canInteract;
}
