/// Chronos (NewTimeLine) client entrypoint — opens on the TikTok-style video feed
/// (ADR-0027). The classic map/timeline experience stays reachable from the feed's overflow
/// menu and the graph/timeline-web view.
///
/// Phase 4-G adds the **account/auth** layer: one app-wide [AuthState] (session JWT + user,
/// driving the [ApiClient] Bearer) is created at boot and a minimal account affordance is
/// overlaid on the home so sign-in / account settings are always reachable without touching
/// the feed-owned home. The feed/overlay (IU2) calls `ensureCanInteract` (see
/// `auth/interaction_gate.dart`) before any write.
library;

import 'package:flutter/material.dart';

import 'account/account_screen.dart';
import 'api/client.dart';
import 'feed/feed_home.dart';
import 'state/auth_state.dart';

void main() => runApp(const ChronosApp());

class ChronosApp extends StatefulWidget {
  const ChronosApp({super.key});

  @override
  State<ChronosApp> createState() => _ChronosAppState();
}

class _ChronosAppState extends State<ChronosApp> {
  // One shared client (carries the Bearer) + the app-wide session state.
  final ApiClient _api = ApiClient();
  late final AuthState _auth = AuthState(api: _api);

  @override
  void initState() {
    super.initState();
    _auth.load(); // restore any persisted session + attach the Bearer
  }

  @override
  void dispose() {
    _auth.dispose();
    _api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Chronos',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorSchemeSeed: const Color(0xFF2E7DF6),
      ),
      home: _HomeWithAccount(api: _api, auth: _auth),
    );
  }
}

/// The feed home with a minimal, always-reachable account/sign-in affordance overlaid in the
/// top-right safe area. Keeps the feed-owned [FeedHome] untouched (Phase 4-G fence) while
/// satisfying the "profile/account entry point + sign-in affordance" requirement.
class _HomeWithAccount extends StatelessWidget {
  const _HomeWithAccount({required this.api, required this.auth});

  final ApiClient api;
  final AuthState auth;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        FeedHome(api: api),
        SafeArea(
          child: Align(
            alignment: Alignment.topRight,
            child: Padding(
              // Sit left of the feed's overflow menu so the two don't overlap.
              padding: const EdgeInsets.only(right: 48, top: 4),
              child: AnimatedBuilder(
                animation: auth,
                builder: (context, _) => IconButton(
                  key: const Key('account-entry'),
                  tooltip: auth.isSignedIn ? 'Account' : 'Sign in',
                  icon: Icon(
                    auth.isSignedIn
                        ? Icons.account_circle
                        : Icons.account_circle_outlined,
                    color: Colors.white,
                  ),
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => AccountScreen(api: api, auth: auth),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
