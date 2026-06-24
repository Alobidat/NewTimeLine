/// The app home (ADR-0027): a full-bleed, immersive scaffold with the three feed tabs
/// **For You / Following / Discover** over a vertical video feed each. The tab bar floats at
/// the top over the video (TikTok-style); a menu affords the classic map/timeline
/// [ExperienceScreen] so the prior experience is never lost.
///
/// Each tab owns its own [VideoFeed] (kept alive across tab switches). All three share one
/// [FeedSource] + [ApiClient] (closed when the home is torn down).
library;

import 'package:flutter/material.dart';

import '../account/account_screen.dart';
import '../api/client.dart';
import '../profile/avatar.dart';
import '../profile/notifications_screen.dart';
import '../profile/profile_screen.dart';
import '../shell/experience_screen.dart';
import '../state/auth_state.dart';
import '../upload/upload_screen.dart';
import 'feed_source.dart';
import 'video_feed.dart';

class FeedHome extends StatefulWidget {
  const FeedHome({super.key, this.api, this.auth});

  /// Injectable for tests; defaults to a real [ApiClient].
  final ApiClient? api;

  /// App-wide session state (IU2). Threaded into the feed so overlay writes gate through
  /// `ensureCanInteract` and the upload/profile affordances know the signed-in user. When
  /// null (older test harnesses) a local in-memory [AuthState] is created so the feed still
  /// runs anonymously.
  final AuthState? auth;

  @override
  State<FeedHome> createState() => _FeedHomeState();
}

class _FeedHomeState extends State<FeedHome>
    with SingleTickerProviderStateMixin {
  late final ApiClient _api = widget.api ?? ApiClient();
  late final bool _ownsApi = widget.api == null;
  late final AuthState _auth = widget.auth ?? AuthState(api: _api);
  late final bool _ownsAuth = widget.auth == null;
  late final FeedSource _source = FeedSource(_api);
  late final TabController _tabs = TabController(
    length: FeedTab.values.length,
    vsync: this,
  );

  /// Unread notification count for the bell badge (0 when signed out).
  int _unread = 0;

  @override
  void initState() {
    super.initState();
    _auth.addListener(_loadUnread);
    _loadUnread();
  }

  Future<void> _loadUnread() async {
    if (!_auth.isSignedIn) {
      if (mounted && _unread != 0) setState(() => _unread = 0);
      return;
    }
    try {
      final n = await _api.notifications(limit: 1);
      if (mounted) setState(() => _unread = n.unread);
    } catch (_) {/* signed-out / offline → leave the badge as-is */}
  }

  void _openNotifications() {
    Navigator.of(context)
        .push(MaterialPageRoute<void>(
          builder: (_) => NotificationsScreen(api: _api, auth: _auth),
        ))
        .then((_) => _loadUnread()); // opening the inbox clears unread server-side
  }

  @override
  void dispose() {
    _auth.removeListener(_loadUnread);
    _tabs.dispose();
    if (_ownsAuth) _auth.dispose();
    if (_ownsApi) _api.close();
    super.dispose();
  }

  void _openUpload() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => UploadScreen(api: _api, auth: _auth),
      ),
    );
  }

  void _openProfile() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ProfileScreen(api: _api, auth: _auth),
      ),
    );
  }

  void _openAccount() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => AccountScreen(api: _api, auth: _auth),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // Transparent (not black): on CanvasKit web the feed clip is an HTML <video> platform
      // view, and an opaque Flutter background paints *over* it and hides it. The black backdrop
      // lives at the document level (web/index.html body) instead, below the video.
      backgroundColor: Colors.transparent,
      extendBodyBehindAppBar: true,
      // Expand: the Scaffold hands the body *loose* constraints, and this Stack's only
      // non-positioned child is the floating tab-bar row (~50px) — without expand the body
      // (and the Positioned.fill feed underneath) collapses to that row's height.
      body: Stack(
        fit: StackFit.expand,
        children: [
          // The feeds fill the screen behind the floating tab bar.
          Positioned.fill(
            child: TabBarView(
              controller: _tabs,
              children: [
                for (final tab in FeedTab.values)
                  VideoFeed(
                    key: ValueKey('videofeed-${tab.slug}'),
                    api: _api,
                    auth: _auth,
                    source: _source,
                    tab: tab,
                    onAddVideo: _openUpload,
                  ),
              ],
            ),
          ),
          // Floating top bar: the three tabs + an overflow menu to the classic experience.
          // topCenter so it pins to the top — as a plain child of the (now expand) Stack it
          // would fill the screen and the Row would centre its tabs vertically.
          Align(
            alignment: Alignment.topCenter,
            child: SafeArea(
              child: Row(
                children: [
                  Expanded(
                    child: TabBar(
                      controller: _tabs,
                      isScrollable: true,
                      tabAlignment: TabAlignment.center,
                      indicatorColor: Colors.white,
                      labelColor: Colors.white,
                      unselectedLabelColor: Colors.white60,
                      dividerColor: Colors.transparent,
                      tabs: [
                        for (final tab in FeedTab.values) Tab(text: tab.label),
                      ],
                    ),
                  ),
                  // Notifications bell (signed-in only) with an unread badge.
                  AnimatedBuilder(
                    animation: _auth,
                    builder: (context, _) {
                      if (!_auth.isSignedIn) return const SizedBox.shrink();
                      return IconButton(
                        key: const Key('notifications-bell'),
                        tooltip: 'Notifications',
                        onPressed: _openNotifications,
                        icon: Badge(
                          isLabelVisible: _unread > 0,
                          label: Text(_unread > 99 ? '99+' : '$_unread'),
                          child: const Icon(Icons.notifications_outlined,
                              color: Colors.white),
                        ),
                      );
                    },
                  ),
                  // Account / sign-in entry — in the Row so it never overlaps the +/⋮.
                  // When signed in, show the user's profile picture (initials fallback);
                  // otherwise the outlined account icon as a sign-in affordance.
                  AnimatedBuilder(
                    animation: _auth,
                    builder: (context, _) {
                      final user = _auth.user;
                      return IconButton(
                        key: const Key('account-entry'),
                        tooltip: _auth.isSignedIn ? 'Account' : 'Sign in',
                        icon: _auth.isSignedIn && user != null
                            ? Avatar(label: user.label, url: user.avatarUrl, radius: 14)
                            : const Icon(
                                Icons.account_circle_outlined,
                                color: Colors.white,
                              ),
                        onPressed: _openAccount,
                      );
                    },
                  ),
                  // (The "+" upload entry moved to the feed's bottom bar — see VideoFeed /
                  // OverlayRail "Add video". The overflow menu below keeps a secondary path.)
                  PopupMenuButton<String>(
                    icon: const Icon(Icons.more_vert, color: Colors.white),
                    onSelected: (v) {
                      if (v == 'experience') {
                        Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => const ExperienceScreen(),
                          ),
                        );
                      } else if (v == 'profile') {
                        _openProfile();
                      } else if (v == 'upload') {
                        _openUpload();
                      }
                    },
                    itemBuilder: (_) => const [
                      PopupMenuItem(
                        key: Key('feed-menu-profile'),
                        value: 'profile',
                        child: ListTile(
                          leading: Icon(Icons.person_outline),
                          title: Text('Profile'),
                          contentPadding: EdgeInsets.zero,
                        ),
                      ),
                      PopupMenuItem(
                        value: 'upload',
                        child: ListTile(
                          leading: Icon(Icons.upload_outlined),
                          title: Text('Upload a clip'),
                          contentPadding: EdgeInsets.zero,
                        ),
                      ),
                      PopupMenuItem(
                        value: 'experience',
                        child: ListTile(
                          leading: Icon(Icons.map_outlined),
                          title: Text('Map & timeline'),
                          contentPadding: EdgeInsets.zero,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
