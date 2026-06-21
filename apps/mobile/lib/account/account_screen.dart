/// Account screen (Phase 4-G, ADR-0026): shows `/account/me` and the GDPR self-service
/// actions — **Download my data** (`GET /account/export`) and **Delete my account**
/// (irreversible `DELETE /account`). Also surfaces the sign-in entry point when anonymous,
/// and the agreement/verify gates' status when signed in.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../auth/login_screen.dart';
import '../auth/verify_email_screen.dart';
import '../auth/agreement_screen.dart';
import '../state/auth_state.dart';

class AccountScreen extends StatefulWidget {
  const AccountScreen({super.key, required this.api, required this.auth});

  final ApiClient api;
  final AuthState auth;

  @override
  State<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends State<AccountScreen> {
  bool _busy = false;

  AuthState get _auth => widget.auth;
  ApiClient get _api => widget.api;

  Future<void> _signIn() async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => LoginScreen(api: _api, auth: _auth)),
    );
    if (mounted) setState(() {});
  }

  Future<void> _signOut() async {
    await _auth.signOut();
    if (mounted) setState(() {});
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _download() async {
    setState(() => _busy = true);
    try {
      final json = await _api.exportData();
      if (!mounted) return;
      // No file/share plugin in deps: show the export so the user can copy it. The raw
      // export URL is also shown for opening externally. TODO(deps): add share_plus /
      // path_provider to save the archive to a file directly.
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Your data export'),
          content: SizedBox(
            width: double.maxFinite,
            child: SingleChildScrollView(
              child: SelectableText(
                json,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 11),
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Clipboard.setData(ClipboardData(text: json)),
              child: const Text('Copy'),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Close'),
            ),
          ],
        ),
      );
    } catch (e) {
      _snack('Export failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete your account?'),
        content: const Text(
          'This permanently and irreversibly removes your account and ALL your data — '
          'comments, reactions, votes, follows, uploads, and activity. This cannot be '
          'undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const Key('confirm-delete'),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete forever'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    setState(() => _busy = true);
    try {
      await _api.deleteAccount();
      await _auth.signOut();
      _snack('Your account was deleted.');
      if (mounted) setState(() {});
    } catch (e) {
      _snack('Deletion failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Account')),
      body: AnimatedBuilder(
        animation: _auth,
        builder: (context, _) {
          if (!_auth.isSignedIn) {
            return _SignedOutBody(onSignIn: _signIn);
          }
          return _SignedInBody(
            user: _auth.user,
            auth: _auth,
            api: _api,
            busy: _busy,
            onDownload: _download,
            onDelete: _delete,
            onSignOut: _signOut,
            onChanged: () => setState(() {}),
          );
        },
      ),
    );
  }
}

class _SignedOutBody extends StatelessWidget {
  const _SignedOutBody({required this.onSignIn});
  final VoidCallback onSignIn;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.account_circle_outlined, size: 64),
          const SizedBox(height: 16),
          const Text('You are browsing anonymously.'),
          const SizedBox(height: 8),
          const Text('Sign in to react, comment, follow, and upload.'),
          const SizedBox(height: 24),
          FilledButton.icon(
            key: const Key('account-sign-in'),
            onPressed: onSignIn,
            icon: const Icon(Icons.login),
            label: const Text('Sign in'),
          ),
        ],
      ),
    );
  }
}

class _SignedInBody extends StatelessWidget {
  const _SignedInBody({
    required this.user,
    required this.auth,
    required this.api,
    required this.busy,
    required this.onDownload,
    required this.onDelete,
    required this.onSignOut,
    required this.onChanged,
  });

  final SessionUser? user;
  final AuthState auth;
  final ApiClient api;
  final bool busy;
  final VoidCallback onDownload;
  final VoidCallback onDelete;
  final VoidCallback onSignOut;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        ListTile(
          leading: const Icon(Icons.account_circle, size: 40),
          title: Text(user?.label ?? 'Signed in'),
          subtitle: Text(user?.email ?? user?.id ?? ''),
        ),
        const Divider(),
        if (!auth.emailVerified)
          _GateTile(
            icon: Icons.mark_email_unread_outlined,
            title: 'Verify your email',
            subtitle: 'Required before you can interact.',
            onTap: () async {
              await Navigator.of(context).push<bool>(
                MaterialPageRoute(
                  builder: (_) => VerifyEmailScreen(api: api, auth: auth),
                ),
              );
              onChanged();
            },
          ),
        if (!auth.agreementAccepted)
          _GateTile(
            icon: Icons.gavel_outlined,
            title: 'Accept the terms',
            subtitle: 'Required before you can interact.',
            onTap: () async {
              await Navigator.of(context).push<bool>(
                MaterialPageRoute(
                  builder: (_) => AgreementScreen(api: api, auth: auth),
                ),
              );
              onChanged();
            },
          ),
        if (auth.canInteract)
          const ListTile(
            leading: Icon(Icons.verified_user, color: Colors.green),
            title: Text('You can interact'),
            subtitle: Text('Verified and agreement accepted.'),
          ),
        const Divider(),
        ListTile(
          key: const Key('download-data'),
          leading: const Icon(Icons.download_outlined),
          title: const Text('Download my data'),
          subtitle: const Text('Export everything we hold about you (GDPR).'),
          enabled: !busy,
          onTap: onDownload,
        ),
        ListTile(
          key: const Key('delete-account'),
          leading: Icon(Icons.delete_forever_outlined,
              color: Theme.of(context).colorScheme.error),
          title: Text('Delete my account',
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
          subtitle: const Text('Irreversible. Removes all your data.'),
          enabled: !busy,
          onTap: onDelete,
        ),
        const Divider(),
        ListTile(
          leading: const Icon(Icons.logout),
          title: const Text('Sign out'),
          enabled: !busy,
          onTap: onSignOut,
        ),
      ],
    );
  }
}

class _GateTile extends StatelessWidget {
  const _GateTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).colorScheme.tertiary;
    return Card(
      child: ListTile(
        leading: Icon(icon, color: c),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
