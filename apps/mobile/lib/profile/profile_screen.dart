/// The signed-in user's profile (Phase 4 IU2, ADR-0028/0029).
///
/// Pulls together the social/recommendation surfaces the rest of Phase 4 built on the server:
/// follow counts (`/follow/counts`), the learned interest profile (`/me/interests`), and the
/// user's own uploads (`/account/uploads`). Each section degrades independently — a failing
/// endpoint shows an empty/placeholder state rather than blanking the screen. Account + GDPR
/// actions live one tap away in [AccountScreen]; this screen is the social "me" view.
library;

import 'package:flutter/material.dart';

import '../account/account_screen.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../auth/login_screen.dart';
import '../domain/time_format.dart';
import '../state/auth_state.dart';
import 'avatar.dart';
import 'follow_list_screen.dart';
import 'friend_requests_screen.dart';
import 'privacy_settings_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key, required this.api, required this.auth});

  final ApiClient api;
  final AuthState auth;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  ApiClient get _api => widget.api;
  AuthState get _auth => widget.auth;

  FollowCounts? _counts;
  InterestProfile? _interests;
  List<EventRead>? _uploads;
  List<EventRead>? _saved;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    if (_auth.isSignedIn) _load();
  }

  /// Load the three sections best-effort and in parallel; a failure leaves that section's
  /// state null (rendered as an empty placeholder), never throwing into the build.
  Future<void> _load() async {
    setState(() => _loading = true);
    final results = await Future.wait([
      _api.followCounts().then<Object?>((v) => v).catchError((_) => null),
      _api.interests().then<Object?>((v) => v).catchError((_) => null),
      _api.myUploads().then<Object?>((v) => v).catchError((_) => null),
      _api.myBookmarks().then<Object?>((v) => v).catchError((_) => null),
    ]);
    if (!mounted) return;
    setState(() {
      _counts = results[0] as FollowCounts?;
      _interests = results[1] as InterestProfile?;
      _uploads = results[2] as List<EventRead>?;
      _saved = results[3] as List<EventRead>?;
      _loading = false;
    });
  }

  Future<void> _signIn() async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => LoginScreen(api: _api, auth: _auth)),
    );
    if (mounted && _auth.isSignedIn) _load();
  }

  void _openAccount() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => AccountScreen(api: _api, auth: _auth),
      ),
    );
  }

  void _openFollowList({required bool followers}) {
    final id = _auth.user?.id;
    if (id == null) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => FollowListScreen(
          api: _api,
          auth: _auth,
          userId: id,
          followers: followers,
          title: followers ? 'Followers' : 'Following',
        ),
      ),
    );
  }

  void _openPrivacy() => Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => PrivacySettingsScreen(api: _api, auth: _auth),
      ));

  void _openFriendRequests() => Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => FriendRequestsScreen(api: _api, auth: _auth),
      ));

  /// Inline bio editor → PATCH /account/me → refresh the session.
  Future<void> _editBio() async {
    final ctrl = TextEditingController(text: _auth.user?.bio ?? '');
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit bio'),
        content: TextField(
          controller: ctrl,
          maxLines: 4,
          maxLength: 2000,
          decoration: const InputDecoration(hintText: 'Tell people about yourself…'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
        ],
      ),
    );
    if (saved != true) return;
    try {
      await _api.updateAccount(bio: ctrl.text.trim());
      await _auth.refresh();
      if (mounted) setState(() {});
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Could not save bio.')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Profile'),
        actions: [
          if (_auth.isSignedIn) ...[
            IconButton(
              key: const Key('profile-friend-requests'),
              tooltip: 'Friend requests',
              icon: const Icon(Icons.group_outlined),
              onPressed: _openFriendRequests,
            ),
            IconButton(
              key: const Key('profile-privacy'),
              tooltip: 'Privacy',
              icon: const Icon(Icons.lock_outline),
              onPressed: _openPrivacy,
            ),
          ],
          IconButton(
            key: const Key('profile-account'),
            tooltip: 'Account & settings',
            icon: const Icon(Icons.settings_outlined),
            onPressed: _openAccount,
          ),
        ],
      ),
      body: AnimatedBuilder(
        animation: _auth,
        builder: (context, _) {
          if (!_auth.isSignedIn) return _SignedOut(onSignIn: _signIn);
          return DefaultTabController(
            length: 2,
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
                  child: Column(
                    children: [
                      _Header(
                        user: _auth.user,
                        counts: _counts,
                        onFollowers: () => _openFollowList(followers: true),
                        onFollowing: () => _openFollowList(followers: false),
                        onEditBio: _editBio,
                      ),
                      const SizedBox(height: 8),
                      if (_loading) const LinearProgressIndicator(),
                      const SizedBox(height: 8),
                      _InterestsSection(profile: _interests),
                    ],
                  ),
                ),
                const TabBar(
                  tabs: [Tab(text: 'Uploads'), Tab(text: 'Saved')],
                ),
                Expanded(
                  child: TabBarView(
                    children: [
                      _EventListTab(
                        keyPrefix: 'upload',
                        items: _uploads,
                        emptyText:
                            'Nothing uploaded yet. Tap + on the feed to add a clip.',
                        onRefresh: _load,
                      ),
                      _EventListTab(
                        keyPrefix: 'saved',
                        items: _saved,
                        emptyText:
                            'No saved clips yet. Tap Save on a clip to keep it here.',
                        onRefresh: _load,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _SignedOut extends StatelessWidget {
  const _SignedOut({required this.onSignIn});
  final VoidCallback onSignIn;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.account_circle_outlined, size: 64),
          const SizedBox(height: 16),
          const Text('Sign in to see your profile, interests, and uploads.'),
          const SizedBox(height: 24),
          FilledButton.icon(
            key: const Key('profile-sign-in'),
            onPressed: onSignIn,
            icon: const Icon(Icons.login),
            label: const Text('Sign in'),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.user,
    required this.counts,
    required this.onFollowers,
    required this.onFollowing,
    required this.onEditBio,
  });
  final SessionUser? user;
  final FollowCounts? counts;
  final VoidCallback onFollowers;
  final VoidCallback onFollowing;
  final VoidCallback onEditBio;

  @override
  Widget build(BuildContext context) {
    final bio = user?.bio;
    return Row(
      children: [
        Avatar(label: user?.label ?? 'You', url: user?.avatarUrl, radius: 28),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(user?.label ?? 'You',
                        style: Theme.of(context).textTheme.titleLarge),
                  ),
                  IconButton(
                    key: const Key('profile-edit-bio'),
                    tooltip: 'Edit bio',
                    visualDensity: VisualDensity.compact,
                    icon: const Icon(Icons.edit_outlined, size: 18),
                    onPressed: onEditBio,
                  ),
                ],
              ),
              if (user?.email != null)
                Text(user!.email!,
                    style: Theme.of(context).textTheme.bodySmall),
              if (bio != null && bio.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(bio, style: Theme.of(context).textTheme.bodyMedium),
                ),
              const SizedBox(height: 6),
              Row(
                children: [
                  _Stat(
                    label: 'Followers',
                    value: counts?.followers ?? 0,
                    onTap: onFollowers,
                  ),
                  const SizedBox(width: 20),
                  _Stat(
                    label: 'Following',
                    value: counts?.following ?? 0,
                    onTap: onFollowing,
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value, this.onTap});
  final String label;
  final int value;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
        child: Column(
          children: [
            Text('$value', style: Theme.of(context).textTheme.titleMedium),
            Text(label, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _InterestsSection extends StatelessWidget {
  const _InterestsSection({required this.profile});
  final InterestProfile? profile;

  @override
  Widget build(BuildContext context) {
    final items = profile?.items ?? const <InterestItem>[];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Your interests',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (items.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text(
              'Interact with the feed — react, follow, watch — and your interests '
              'will show up here.',
            ),
          )
        else
          Wrap(
            spacing: 8,
            runSpacing: 4,
            children: [
              for (final it in items.take(20))
                Chip(label: Text(it.label), avatar: _kindIcon(it.kind)),
            ],
          ),
      ],
    );
  }

  Icon? _kindIcon(String kind) => switch (kind) {
        'entities' => const Icon(Icons.person_outline, size: 18),
        'places' => const Icon(Icons.place_outlined, size: 18),
        'categories' => const Icon(Icons.label_outline, size: 18),
        'sources' => const Icon(Icons.public, size: 18),
        _ => null,
      };
}

/// One profile tab: a pull-to-refresh, scrollable list of the user's events (uploads or
/// saved). Always scrollable (even when empty) so the [RefreshIndicator] works.
class _EventListTab extends StatelessWidget {
  const _EventListTab({
    required this.keyPrefix,
    required this.items,
    required this.emptyText,
    required this.onRefresh,
  });

  final String keyPrefix;
  final List<EventRead>? items;
  final String emptyText;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    final list = items ?? const <EventRead>[];
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: list.isEmpty
          ? ListView(
              padding: const EdgeInsets.all(24),
              children: [Text(emptyText, textAlign: TextAlign.center)],
            )
          : ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: list.length,
              itemBuilder: (context, i) {
                final e = list[i];
                return ListTile(
                  key: Key('$keyPrefix-${e.id}'),
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.movie_outlined),
                  title:
                      Text(e.title, maxLines: 2, overflow: TextOverflow.ellipsis),
                  subtitle: Text(
                    [
                      formatYear(e.tStart),
                      if (e.geoLabel != null) e.geoLabel!,
                    ].join(' · '),
                  ),
                );
              },
            ),
    );
  }
}
