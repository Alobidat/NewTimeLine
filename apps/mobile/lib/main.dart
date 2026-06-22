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
import 'feed/feed_source.dart';
import 'feed/video_feed.dart';
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
///
/// Also handles **share deep links**: when the app is opened with `?event=<id>` (the link
/// shape produced by the feed's share sheet, see `feed/share.dart`), it fetches that event
/// once the first frame is up and opens it in a focused immersive feed — so a shared link
/// lands the recipient on the clip rather than a generic feed.
class _HomeWithAccount extends StatefulWidget {
  const _HomeWithAccount({required this.api, required this.auth});

  final ApiClient api;
  final AuthState auth;

  @override
  State<_HomeWithAccount> createState() => _HomeWithAccountState();
}

class _HomeWithAccountState extends State<_HomeWithAccount> {
  @override
  void initState() {
    super.initState();
    final eventId = Uri.base.queryParameters['event'];
    if (eventId != null && eventId.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _openSharedEvent(eventId));
    }
  }

  /// Open a shared-link event in a focused immersive feed seeded with it. Best-effort: a bad
  /// or unknown id silently leaves the user on the normal feed.
  Future<void> _openSharedEvent(String eventId) async {
    try {
      final event = await widget.api.event(eventId);
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => Scaffold(
            backgroundColor: Colors.black,
            body: VideoFeed(
              api: widget.api,
              auth: widget.auth,
              source: SeededFeedSource(FeedSource(widget.api), event),
              tab: FeedTab.forYou,
            ),
          ),
        ),
      );
    } catch (_) {
      // Unknown/garbage id — stay on the feed.
    }
  }

  @override
  Widget build(BuildContext context) {
    final api = widget.api;
    final auth = widget.auth;
    // The feed home owns the upload (+) and profile affordances now that AuthState is
    // threaded into it (IU2). The minimal top-right account/sign-in shortcut stays as a
    // quick always-reachable entry to the account/GDPR settings.
    return Stack(
      children: [
        // Positioned.fill so the Scaffold gets *tight* full-screen constraints. As a bare
        // (non-positioned) Stack child it would only get loose constraints and the feed's
        // Scaffold body collapses to the height of its tab-bar row — the clip then only looks
        // full because its <video> self-sizes to 100vh, while the Flutter overlays (the action
        // rail + caption) shrink to a thin strip at the top.
        Positioned.fill(child: FeedHome(api: api, auth: auth)),
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
