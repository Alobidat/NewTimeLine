/// A public user profile (any user by id): avatar, name, bio, follower/following/friends
/// counts, a Follow + a Friend button, and Posts / Interactions tabs — each shown only when
/// the viewer's audience permits (``can_view_*``). Opened from a comment author, a follower/
/// following list row, or the feed creator.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../auth/interaction_gate.dart';
import '../domain/time_format.dart';
import '../state/auth_state.dart';
import 'avatar.dart';
import 'follow_list_screen.dart';

class UserProfilePage extends StatefulWidget {
  const UserProfilePage({
    super.key,
    required this.api,
    required this.auth,
    required this.userId,
  });

  final ApiClient api;
  final AuthState auth;
  final String userId;

  @override
  State<UserProfilePage> createState() => _UserProfilePageState();
}

class _UserProfilePageState extends State<UserProfilePage> {
  UserProfile? _profile;
  Object? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final p = await widget.api.userProfile(widget.userId);
      if (mounted) setState(() => _profile = p);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _act(Future<void> Function() action) async {
    if (_busy) return;
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    setState(() => _busy = true);
    try {
      await action();
      if (mounted) await _load();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Could not complete that.')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _toggleFollow() {
    final p = _profile!;
    _act(() => p.isFollowing
        ? widget.api.unfollow('user', p.id)
        : widget.api.follow('user', p.id));
  }

  void _friendAction() {
    final p = _profile!;
    switch (p.friendState) {
      case 'none':
        _act(() => widget.api.sendFriendRequest(p.id).then((_) {}));
      case 'incoming':
        if (p.friendshipId != null) {
          _act(() => widget.api.acceptFriend(p.friendshipId!).then((_) {}));
        }
      case 'outgoing':
        if (p.friendshipId != null) _act(() => widget.api.declineFriend(p.friendshipId!));
      case 'friends':
        _act(() => widget.api.removeFriend(p.id));
    }
  }

  ({String label, IconData icon}) get _friendLabel => switch (_profile!.friendState) {
        'friends' => (label: 'Friends', icon: Icons.people),
        'incoming' => (label: 'Accept', icon: Icons.person_add_alt_1),
        'outgoing' => (label: 'Requested', icon: Icons.hourglass_top),
        _ => (label: 'Add friend', icon: Icons.person_add_alt),
      };

  void _openList({required bool followers}) {
    final p = _profile!;
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => FollowListScreen(
        api: widget.api, auth: widget.auth, userId: p.id,
        followers: followers, title: followers ? 'Followers' : 'Following',
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final p = _profile;
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(),
        body: Center(child: Text('Could not load profile.\n$_error', textAlign: TextAlign.center)),
      );
    }
    if (p == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final tabs = <Tab>[
      if (p.canViewPosts) const Tab(text: 'Posts'),
      if (p.canViewInteractions) const Tab(text: 'Activity'),
    ];
    return DefaultTabController(
      length: tabs.isEmpty ? 1 : tabs.length,
      child: Scaffold(
        appBar: AppBar(title: Text(p.label)),
        body: Column(
          children: [
            _Header(
              profile: p,
              busy: _busy,
              friend: _friendLabel,
              onFollow: _toggleFollow,
              onFriend: _friendAction,
              onFollowers: p.canViewFollowers ? () => _openList(followers: true) : null,
              onFollowing: p.canViewFollowing ? () => _openList(followers: false) : null,
            ),
            if (tabs.isNotEmpty) TabBar(tabs: tabs),
            Expanded(
              child: tabs.isEmpty
                  ? const Center(child: Text('This profile is private.'))
                  : TabBarView(
                      children: [
                        if (p.canViewPosts) _PostsTab(api: widget.api, userId: p.id),
                        if (p.canViewInteractions)
                          _ActivityTab(api: widget.api, userId: p.id),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.profile,
    required this.busy,
    required this.friend,
    required this.onFollow,
    required this.onFriend,
    required this.onFollowers,
    required this.onFollowing,
  });
  final UserProfile profile;
  final bool busy;
  final ({String label, IconData icon}) friend;
  final VoidCallback onFollow;
  final VoidCallback onFriend;
  final VoidCallback? onFollowers;
  final VoidCallback? onFollowing;

  @override
  Widget build(BuildContext context) {
    final p = profile;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Column(
        children: [
          Avatar(label: p.label, url: p.avatarUrl, radius: 40),
          const SizedBox(height: 10),
          Text(p.label, style: Theme.of(context).textTheme.titleLarge),
          Text('@${p.handle}',
              style: Theme.of(context).textTheme.bodySmall
                  ?.copyWith(color: Theme.of(context).colorScheme.outline)),
          if (p.bio != null && p.bio!.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(p.bio!, textAlign: TextAlign.center),
          ],
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _Stat(label: 'Followers', value: p.followers, onTap: onFollowers),
              const SizedBox(width: 24),
              _Stat(label: 'Following', value: p.following, onTap: onFollowing),
              const SizedBox(width: 24),
              _Stat(label: 'Friends', value: p.friends),
            ],
          ),
          if (!p.isSelf) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: FilledButton.icon(
                    key: const Key('profile-follow-toggle'),
                    onPressed: busy ? null : onFollow,
                    icon: Icon(p.isFollowing ? Icons.how_to_reg : Icons.person_add_alt_1),
                    label: Text(p.isFollowing ? 'Following' : 'Follow'),
                    style: p.isFollowing
                        ? FilledButton.styleFrom(
                            backgroundColor:
                                Theme.of(context).colorScheme.surfaceContainerHighest,
                            foregroundColor: Theme.of(context).colorScheme.onSurface)
                        : null,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    key: const Key('profile-friend-toggle'),
                    onPressed: busy ? null : onFriend,
                    icon: Icon(friend.icon),
                    label: Text(friend.label),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
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
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Column(children: [
          Text('$value', style: Theme.of(context).textTheme.titleMedium),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
        ]),
      ),
    );
  }
}

/// The user's published posts as a thumbnail grid.
class _PostsTab extends StatefulWidget {
  const _PostsTab({required this.api, required this.userId});
  final ApiClient api;
  final String userId;
  @override
  State<_PostsTab> createState() => _PostsTabState();
}

class _PostsTabState extends State<_PostsTab>
    with AutomaticKeepAliveClientMixin {
  late final Future<List<EventRead>> _future = widget.api.userUploads(widget.userId);
  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return FutureBuilder<List<EventRead>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        final posts = snap.data ?? const <EventRead>[];
        if (posts.isEmpty) {
          return const Center(child: Text('No posts yet.'));
        }
        return GridView.builder(
          padding: const EdgeInsets.all(8),
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 3, crossAxisSpacing: 6, mainAxisSpacing: 6, childAspectRatio: 0.8,
          ),
          itemCount: posts.length,
          itemBuilder: (_, i) {
            final e = posts[i];
            return Container(
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(8),
              ),
              padding: const EdgeInsets.all(8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.movie_outlined, size: 22),
                  const Spacer(),
                  Text(e.title, maxLines: 3, overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall),
                  if (e.visibility != 'public')
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Icon(
                        e.visibility == 'friends' ? Icons.people : Icons.group,
                        size: 13, color: Theme.of(context).colorScheme.outline,
                      ),
                    ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

/// The user's recent interactions on visible events.
class _ActivityTab extends StatefulWidget {
  const _ActivityTab({required this.api, required this.userId});
  final ApiClient api;
  final String userId;
  @override
  State<_ActivityTab> createState() => _ActivityTabState();
}

class _ActivityTabState extends State<_ActivityTab>
    with AutomaticKeepAliveClientMixin {
  late final Future<List<InteractionItem>> _future =
      widget.api.userInteractions(widget.userId);
  @override
  bool get wantKeepAlive => true;

  IconData _icon(String kind) => switch (kind) {
        'react' => Icons.favorite,
        'comment' => Icons.mode_comment_outlined,
        'promote' => Icons.arrow_upward,
        'follow' => Icons.person_add_alt_1,
        _ => Icons.bolt,
      };

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return FutureBuilder<List<InteractionItem>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        final items = snap.data ?? const <InteractionItem>[];
        if (items.isEmpty) return const Center(child: Text('No recent activity.'));
        return ListView.separated(
          itemCount: items.length,
          separatorBuilder: (_, _) => const Divider(height: 1),
          itemBuilder: (_, i) {
            final it = items[i];
            return ListTile(
              leading: Icon(_icon(it.kind)),
              title: Text(it.event.title, maxLines: 2, overflow: TextOverflow.ellipsis),
              subtitle: Text('${it.kind} · ${formatYear(it.event.tStart)}'),
            );
          },
        );
      },
    );
  }
}
