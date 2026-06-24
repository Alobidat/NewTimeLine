/// Friend requests inbox: incoming requests (accept/decline) + outgoing (cancel). Rows open
/// the requester's profile.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../state/auth_state.dart';
import 'avatar.dart';
import 'user_profile_page.dart';

class FriendRequestsScreen extends StatefulWidget {
  const FriendRequestsScreen({super.key, required this.api, required this.auth});
  final ApiClient api;
  final AuthState auth;

  @override
  State<FriendRequestsScreen> createState() => _FriendRequestsScreenState();
}

class _FriendRequestsScreenState extends State<FriendRequestsScreen> {
  List<FriendRequest>? _incoming;
  List<FriendRequest>? _outgoing;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await widget.api.friendRequests();
      if (mounted) {
        setState(() {
          _incoming = r.incoming;
          _outgoing = r.outgoing;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _do(Future<void> Function() action) async {
    try {
      await action();
      await _load();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Could not complete that.')));
      }
    }
  }

  void _openProfile(String id) => Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => UserProfilePage(api: widget.api, auth: widget.auth, userId: id),
      ));

  @override
  Widget build(BuildContext context) {
    final incoming = _incoming ?? const <FriendRequest>[];
    final outgoing = _outgoing ?? const <FriendRequest>[];
    return Scaffold(
      appBar: AppBar(title: const Text('Friend requests')),
      body: _error != null
          ? Center(child: Text('Could not load.\n$_error', textAlign: TextAlign.center))
          : (_incoming == null)
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  children: [
                    if (incoming.isEmpty && outgoing.isEmpty)
                      const Padding(
                        padding: EdgeInsets.all(32),
                        child: Center(child: Text('No pending requests.')),
                      ),
                    if (incoming.isNotEmpty)
                      const Padding(
                        padding: EdgeInsets.fromLTRB(16, 12, 16, 4),
                        child: Text('Incoming', style: TextStyle(fontWeight: FontWeight.w600)),
                      ),
                    for (final r in incoming)
                      ListTile(
                        onTap: () => _openProfile(r.user.id),
                        leading: Avatar(label: r.user.label, url: r.user.avatarUrl, radius: 20),
                        title: Text(r.user.label),
                        subtitle: Text('@${r.user.handle}'),
                        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                          IconButton(
                            tooltip: 'Accept',
                            icon: const Icon(Icons.check_circle, color: Colors.green),
                            onPressed: () => _do(() => widget.api.acceptFriend(r.friendshipId).then((_) {})),
                          ),
                          IconButton(
                            tooltip: 'Decline',
                            icon: const Icon(Icons.cancel_outlined),
                            onPressed: () => _do(() => widget.api.declineFriend(r.friendshipId)),
                          ),
                        ]),
                      ),
                    if (outgoing.isNotEmpty)
                      const Padding(
                        padding: EdgeInsets.fromLTRB(16, 12, 16, 4),
                        child: Text('Sent', style: TextStyle(fontWeight: FontWeight.w600)),
                      ),
                    for (final r in outgoing)
                      ListTile(
                        onTap: () => _openProfile(r.user.id),
                        leading: Avatar(label: r.user.label, url: r.user.avatarUrl, radius: 20),
                        title: Text(r.user.label),
                        subtitle: Text('@${r.user.handle}'),
                        trailing: TextButton(
                          onPressed: () => _do(() => widget.api.declineFriend(r.friendshipId)),
                          child: const Text('Cancel'),
                        ),
                      ),
                  ],
                ),
    );
  }
}
