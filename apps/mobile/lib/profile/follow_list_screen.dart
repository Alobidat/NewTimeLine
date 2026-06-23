/// A followers/following list: each row is a user (avatar + name + handle) with a Follow/
/// Following toggle, tappable to open that user's profile. Used for both "who follows X" and
/// "who X follows".
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../auth/interaction_gate.dart';
import '../state/auth_state.dart';
import 'avatar.dart';
import 'user_profile_page.dart';

class FollowListScreen extends StatefulWidget {
  const FollowListScreen({
    super.key,
    required this.api,
    required this.auth,
    required this.userId,
    required this.followers,
    required this.title,
  });

  final ApiClient api;
  final AuthState auth;
  final String userId;

  /// True → who follows [userId]; false → who [userId] follows.
  final bool followers;
  final String title;

  @override
  State<FollowListScreen> createState() => _FollowListScreenState();
}

class _FollowListScreenState extends State<FollowListScreen> {
  List<UserSummary>? _items;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final list = widget.followers
          ? await widget.api.userFollowers(widget.userId)
          : await widget.api.userFollowing(widget.userId);
      if (mounted) setState(() => _items = list);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  void _openProfile(String id) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => UserProfilePage(api: widget.api, auth: widget.auth, userId: id),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: _error != null
          ? Center(child: Text('Could not load.\n$_error', textAlign: TextAlign.center))
          : items == null
              ? const Center(child: CircularProgressIndicator())
              : items.isEmpty
                  ? Center(
                      child: Text(
                        widget.followers ? 'No followers yet.' : 'Not following anyone yet.',
                      ),
                    )
                  : ListView.separated(
                      itemCount: items.length,
                      separatorBuilder: (_, _) => const Divider(height: 1),
                      itemBuilder: (_, i) => _UserRow(
                        api: widget.api,
                        auth: widget.auth,
                        user: items[i],
                        onOpen: () => _openProfile(items[i].id),
                      ),
                    ),
    );
  }
}

/// One user row with an inline follow toggle (optimistic).
class _UserRow extends StatefulWidget {
  const _UserRow({
    required this.api,
    required this.auth,
    required this.user,
    required this.onOpen,
  });
  final ApiClient api;
  final AuthState auth;
  final UserSummary user;
  final VoidCallback onOpen;

  @override
  State<_UserRow> createState() => _UserRowState();
}

class _UserRowState extends State<_UserRow> {
  late bool _following = widget.user.following;
  bool _busy = false;

  Future<void> _toggle() async {
    if (_busy) return;
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    setState(() => _busy = true);
    final want = !_following;
    setState(() => _following = want); // optimistic
    try {
      want
          ? await widget.api.follow('user', widget.user.id)
          : await widget.api.unfollow('user', widget.user.id);
    } catch (_) {
      if (mounted) setState(() => _following = !want); // rollback
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final u = widget.user;
    return ListTile(
      onTap: widget.onOpen,
      leading: Avatar(label: u.label, url: u.avatarUrl, radius: 20),
      title: Text(u.label),
      subtitle: Text('@${u.handle}'),
      trailing: OutlinedButton(
        onPressed: _busy ? null : _toggle,
        child: Text(_following ? 'Following' : 'Follow'),
      ),
    );
  }
}
