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
  List<FollowedItem>? _items;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      // Followers are always users; following can also be entities (NASA) + events.
      final list = widget.followers
          ? (await widget.api.userFollowers(widget.userId))
              .map(FollowedItem.fromUser)
              .toList()
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
                      itemBuilder: (_, i) => _FollowedRow(
                        api: widget.api,
                        auth: widget.auth,
                        item: items[i],
                        // Only users have a personal profile to open.
                        onOpen: items[i].kind == 'user'
                            ? () => _openProfile(items[i].id)
                            : null,
                      ),
                    ),
    );
  }
}

/// One followed-target row (user / entity / event) with an inline follow toggle (optimistic).
class _FollowedRow extends StatefulWidget {
  const _FollowedRow({
    required this.api,
    required this.auth,
    required this.item,
    required this.onOpen,
  });
  final ApiClient api;
  final AuthState auth;
  final FollowedItem item;
  final VoidCallback? onOpen;

  @override
  State<_FollowedRow> createState() => _FollowedRowState();
}

class _FollowedRowState extends State<_FollowedRow> {
  late bool _following = widget.item.following;
  bool _busy = false;

  Future<void> _toggle() async {
    if (_busy) return;
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    setState(() => _busy = true);
    final want = !_following;
    setState(() => _following = want); // optimistic
    try {
      want
          ? await widget.api.follow(widget.item.kind, widget.item.id)
          : await widget.api.unfollow(widget.item.kind, widget.item.id);
    } catch (_) {
      if (mounted) setState(() => _following = !want); // rollback
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final it = widget.item;
    final isUser = it.kind == 'user';
    return ListTile(
      onTap: widget.onOpen,
      leading: isUser
          ? Avatar(label: it.name, url: it.avatarUrl, radius: 20)
          : CircleAvatar(
              radius: 20,
              child: Icon(it.kind == 'event' ? Icons.event : Icons.tag),
            ),
      title: Text(it.name),
      subtitle: Text(
        isUser ? '@${it.handle ?? ''}' : (it.kind == 'event' ? 'Event' : 'Topic'),
      ),
      trailing: OutlinedButton(
        onPressed: _busy ? null : _toggle,
        child: Text(_following ? 'Following' : 'Follow'),
      ),
    );
  }
}
