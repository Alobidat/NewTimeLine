/// A public user profile (any user by id): avatar, name, reputation, follower/following
/// counts (tap to open the lists), and a Follow/Unfollow button (interaction-gated; hidden for
/// your own profile). Opened from a comment author, a follower/following list row, etc.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../auth/interaction_gate.dart';
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

  Future<void> _toggleFollow() async {
    final p = _profile;
    if (p == null || _busy) return;
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    setState(() => _busy = true);
    final want = !p.isFollowing;
    try {
      want
          ? await widget.api.follow('user', p.id)
          : await widget.api.unfollow('user', p.id);
      if (mounted) await _load();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not update follow.')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _openList({required bool followers}) {
    final p = _profile;
    if (p == null) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => FollowListScreen(
          api: widget.api,
          auth: widget.auth,
          userId: p.id,
          followers: followers,
          title: followers ? 'Followers' : 'Following',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final p = _profile;
    return Scaffold(
      appBar: AppBar(title: Text(p?.label ?? 'Profile')),
      body: _error != null
          ? Center(child: Text('Could not load profile.\n$_error', textAlign: TextAlign.center))
          : p == null
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: const EdgeInsets.all(20),
                  children: [
                    Center(child: Avatar(label: p.label, url: p.avatarUrl, radius: 44)),
                    const SizedBox(height: 12),
                    Center(
                      child: Text(p.label, style: Theme.of(context).textTheme.headlineSmall),
                    ),
                    Center(
                      child: Text('@${p.handle}',
                          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                color: Theme.of(context).colorScheme.outline,
                              )),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        _StatButton(
                          label: 'Followers',
                          value: p.followers,
                          onTap: () => _openList(followers: true),
                        ),
                        const SizedBox(width: 28),
                        _StatButton(
                          label: 'Following',
                          value: p.following,
                          onTap: () => _openList(followers: false),
                        ),
                        const SizedBox(width: 28),
                        _StatButton(label: 'Reputation', value: p.reputation),
                      ],
                    ),
                    const SizedBox(height: 20),
                    if (!p.isSelf)
                      FilledButton.icon(
                        key: const Key('profile-follow-toggle'),
                        onPressed: _busy ? null : _toggleFollow,
                        icon: Icon(p.isFollowing ? Icons.how_to_reg : Icons.person_add_alt_1),
                        label: Text(p.isFollowing ? 'Following' : 'Follow'),
                        style: p.isFollowing
                            ? FilledButton.styleFrom(
                                backgroundColor:
                                    Theme.of(context).colorScheme.surfaceContainerHighest,
                                foregroundColor: Theme.of(context).colorScheme.onSurface,
                              )
                            : null,
                      ),
                  ],
                ),
    );
  }
}

class _StatButton extends StatelessWidget {
  const _StatButton({required this.label, required this.value, this.onTap});
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
        child: Column(
          children: [
            Text('$value', style: Theme.of(context).textTheme.titleLarge),
            Text(label, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
