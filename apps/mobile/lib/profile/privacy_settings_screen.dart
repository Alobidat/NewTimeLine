/// Privacy settings: pick the minimum audience for each profile facet (bio, posts, followers,
/// following, activity) and the default audience for new posts. Saving PATCHes /account/me and
/// refreshes the session.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../state/auth_state.dart';

class PrivacySettingsScreen extends StatefulWidget {
  const PrivacySettingsScreen({super.key, required this.api, required this.auth});
  final ApiClient api;
  final AuthState auth;

  @override
  State<PrivacySettingsScreen> createState() => _PrivacySettingsScreenState();
}

class _PrivacySettingsScreenState extends State<PrivacySettingsScreen> {
  // Facet audiences allow only_me; post audience does not.
  static const _facet = ['public', 'followers', 'friends', 'only_me'];
  static const _post = ['public', 'followers', 'friends'];

  late PrivacySettings _p = widget.auth.user?.privacy ?? PrivacySettings();
  bool _busy = false;

  String _label(String a) => switch (a) {
        'public' => 'Public',
        'followers' => 'Followers',
        'friends' => 'Friends',
        'only_me' => 'Only me',
        _ => a,
      };

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      final updated = await widget.api.updateAccount(privacy: _p);
      await widget.auth.refresh();
      if (mounted) {
        setState(() => _p = updated.privacy);
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Privacy updated.')));
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Could not save: $e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _picker(String title, String value, List<String> options, ValueChanged<String> onChanged) {
    return ListTile(
      title: Text(title),
      trailing: DropdownButton<String>(
        value: value,
        onChanged: _busy ? null : (v) => onChanged(v ?? value),
        items: [for (final o in options) DropdownMenuItem(value: o, child: Text(_label(o)))],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Privacy'),
        actions: [
          TextButton(
            onPressed: _busy ? null : _save,
            child: _busy
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Save'),
          ),
        ],
      ),
      body: ListView(
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Text('Who can see…', style: TextStyle(fontWeight: FontWeight.w600)),
          ),
          _picker('Bio', _p.bio, _facet, (v) => setState(() => _p = _p.copyWith(bio: v))),
          _picker('Posts', _p.posts, _facet, (v) => setState(() => _p = _p.copyWith(posts: v))),
          _picker('Followers list', _p.followers, _facet,
              (v) => setState(() => _p = _p.copyWith(followers: v))),
          _picker('Following list', _p.following, _facet,
              (v) => setState(() => _p = _p.copyWith(following: v))),
          _picker('Activity', _p.interactions, _facet,
              (v) => setState(() => _p = _p.copyWith(interactions: v))),
          const Divider(),
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Text('New posts', style: TextStyle(fontWeight: FontWeight.w600)),
          ),
          _picker('Default audience', _p.defaultPostAudience, _post,
              (v) => setState(() => _p = _p.copyWith(defaultPostAudience: v))),
        ],
      ),
    );
  }
}
