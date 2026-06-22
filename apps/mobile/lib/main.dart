/// Chronos (NewTimeLine) client entrypoint — opens on the TikTok-style video feed
/// (ADR-0027). The classic map/timeline experience stays reachable from the feed's overflow
/// menu and the graph/timeline-web view.
///
/// Phase 4-G adds the **account/auth** layer: one app-wide [AuthState] (session JWT + user,
/// driving the [ApiClient] Bearer) is created at boot and threaded into [FeedHome], whose top
/// bar carries the account/sign-in entry alongside the upload + overflow actions. The
/// feed/overlay (IU2) calls `ensureCanInteract` (see `auth/interaction_gate.dart`) before any
/// write.
library;

import 'package:flutter/material.dart';

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

/// Hosts [FeedHome] (which owns the account/sign-in entry in its top bar) and handles
/// **share deep links**: when the app is opened with `?event=<id>` (the link
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
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => _openSharedEvent(eventId),
      );
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
    // The feed home owns the entire screen, including its top bar (tabs + account/sign-in +
    // upload + overflow menu) — laid out together so the trailing icons never overlap. Share
    // deep links (?event=) are handled in initState above.
    return FeedHome(api: widget.api, auth: widget.auth);
  }
}
