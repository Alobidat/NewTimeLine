/// The notifications inbox (Phase 5): who followed you or liked / commented / replied /
/// reposted your content. Opening the screen marks everything read (clears the bell badge).
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../state/auth_state.dart';
import 'avatar.dart';
import 'user_profile_page.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key, required this.api, required this.auth});

  final ApiClient api;
  final AuthState auth;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  List<AppNotification>? _items;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final list = await widget.api.notifications();
      if (!mounted) return;
      setState(() => _items = list.items);
      // Opening the inbox clears the unread badge.
      widget.api.markNotificationsRead().catchError((_) {});
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  void _openActor(AppNotification n) {
    final id = n.actor?.id;
    if (id == null) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            UserProfilePage(api: widget.api, auth: widget.auth, userId: id),
      ),
    );
  }

  IconData _icon(String kind) => switch (kind) {
        'follow' => Icons.person_add_alt_1,
        'like' => Icons.favorite,
        'comment' || 'reply' => Icons.mode_comment,
        'repost' => Icons.repeat,
        _ => Icons.notifications,
      };

  Color _iconColor(String kind) => switch (kind) {
        'like' => Colors.redAccent,
        'repost' => Colors.green,
        'follow' => Colors.blueAccent,
        _ => Colors.grey,
      };

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
      body: _error != null
          ? Center(child: Text('Could not load.\n$_error', textAlign: TextAlign.center))
          : items == null
              ? const Center(child: CircularProgressIndicator())
              : items.isEmpty
                  ? const _Empty()
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.separated(
                        itemCount: items.length,
                        separatorBuilder: (_, _) => const Divider(height: 1),
                        itemBuilder: (_, i) {
                          final n = items[i];
                          final name = n.actor?.label ?? 'Someone';
                          return ListTile(
                            key: Key('notif-$i'),
                            onTap: () => _openActor(n),
                            leading: Stack(
                              clipBehavior: Clip.none,
                              children: [
                                Avatar(
                                  label: name,
                                  url: n.actor?.avatarUrl,
                                  radius: 22,
                                ),
                                Positioned(
                                  bottom: -2,
                                  right: -2,
                                  child: CircleAvatar(
                                    radius: 9,
                                    backgroundColor: _iconColor(n.kind),
                                    child: Icon(_icon(n.kind),
                                        size: 11, color: Colors.white),
                                  ),
                                ),
                              ],
                            ),
                            title: Text.rich(
                              TextSpan(children: [
                                TextSpan(
                                  text: name,
                                  style: const TextStyle(fontWeight: FontWeight.w700),
                                ),
                                TextSpan(text: ' ${n.message}'),
                              ]),
                            ),
                            subtitle: (n.eventTitle != null)
                                ? Text(n.eventTitle!,
                                    maxLines: 1, overflow: TextOverflow.ellipsis)
                                : null,
                            trailing: Text(
                              _ago(n.createdAt),
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty();
  @override
  Widget build(BuildContext context) => const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.notifications_none, size: 56, color: Colors.grey),
            SizedBox(height: 12),
            Text('No notifications yet.'),
            SizedBox(height: 4),
            Text("When people react to your posts, you'll see it here.",
                style: TextStyle(color: Colors.grey)),
          ],
        ),
      );
}

/// Compact "time ago" (e.g. "3h", "2d") from [t] to now; empty when null.
String _ago(DateTime? t) {
  if (t == null) return '';
  final d = DateTime.now().difference(t);
  if (d.inMinutes < 1) return 'now';
  if (d.inMinutes < 60) return '${d.inMinutes}m';
  if (d.inHours < 24) return '${d.inHours}h';
  if (d.inDays < 7) return '${d.inDays}d';
  return '${(d.inDays / 7).floor()}w';
}
