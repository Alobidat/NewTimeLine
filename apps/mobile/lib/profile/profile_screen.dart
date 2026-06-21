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
    ]);
    if (!mounted) return;
    setState(() {
      _counts = results[0] as FollowCounts?;
      _interests = results[1] as InterestProfile?;
      _uploads = results[2] as List<EventRead>?;
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Profile'),
        actions: [
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
          return RefreshIndicator(
            onRefresh: _load,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _Header(user: _auth.user, counts: _counts),
                const SizedBox(height: 8),
                if (_loading) const LinearProgressIndicator(),
                const Divider(),
                _InterestsSection(profile: _interests),
                const Divider(),
                _UploadsSection(uploads: _uploads),
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
  const _Header({required this.user, required this.counts});
  final SessionUser? user;
  final FollowCounts? counts;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const CircleAvatar(radius: 28, child: Icon(Icons.person, size: 32)),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(user?.label ?? 'You',
                  style: Theme.of(context).textTheme.titleLarge),
              if (user?.email != null)
                Text(user!.email!,
                    style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 6),
              Row(
                children: [
                  _Stat(label: 'Followers', value: counts?.followers ?? 0),
                  const SizedBox(width: 20),
                  _Stat(label: 'Following', value: counts?.following ?? 0),
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
  const _Stat({required this.label, required this.value});
  final String label;
  final int value;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text('$value', style: Theme.of(context).textTheme.titleMedium),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
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

class _UploadsSection extends StatelessWidget {
  const _UploadsSection({required this.uploads});
  final List<EventRead>? uploads;

  @override
  Widget build(BuildContext context) {
    final items = uploads ?? const <EventRead>[];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Your uploads',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (items.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text('Nothing uploaded yet. Tap + on the feed to add a clip.'),
          )
        else
          for (final e in items)
            ListTile(
              key: Key('upload-${e.id}'),
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.movie_outlined),
              title: Text(e.title, maxLines: 2, overflow: TextOverflow.ellipsis),
              subtitle: Text(
                [
                  formatYear(e.tStart),
                  if (e.geoLabel != null) e.geoLabel!,
                ].join(' · '),
              ),
            ),
      ],
    );
  }
}
