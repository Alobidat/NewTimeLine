/// Sign-in screen (Phase 4-G, ADR-0026): no registration form — list the backend's
/// config-driven providers as buttons; tapping one runs the OAuth2/OIDC auth-code+PKCE
/// flow. On success the session JWT is adopted by [AuthState] and `/account/me` is fetched.
///
/// Provider set is **config-driven and may be empty** until credentials are configured —
/// this screen renders that case as a clear "no sign-in providers configured" note with a
/// dev hint, never a broken/empty list.
///
/// Flow handoff: the actual browser launch + callback handling lives in
/// [runOAuthFlow] (`oauth_flow.dart`) so the platform differences (web redirect vs external
/// browser) are isolated and this screen stays declarative.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../state/auth_state.dart';
import 'oauth_flow.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.api, required this.auth});

  final ApiClient api;
  final AuthState auth;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  late Future<List<AuthProvider>> _providers;
  String? _busyProvider;
  String? _error;

  @override
  void initState() {
    super.initState();
    _providers = widget.api.authProviders();
  }

  Future<void> _signIn(AuthProvider provider) async {
    setState(() {
      _busyProvider = provider.name;
      _error = null;
    });
    try {
      final session = await runOAuthFlow(
        widget.api,
        provider.name,
        prompter: buildContextPrompter(context),
      );
      if (session == null) {
        // User cancelled / closed the browser.
        if (mounted) setState(() => _busyProvider = null);
        return;
      }
      await widget.auth.adopt(session);
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) {
        setState(() {
          _busyProvider = null;
          _error = 'Sign-in failed: $e';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sign in')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: FutureBuilder<List<AuthProvider>>(
            future: _providers,
            builder: (context, snap) {
              if (snap.connectionState != ConnectionState.done) {
                return const CircularProgressIndicator();
              }
              if (snap.hasError) {
                return _Message(
                  icon: Icons.error_outline,
                  title: "Couldn't load sign-in options",
                  detail: '${snap.error}',
                );
              }
              final providers = snap.data ?? const [];
              if (providers.isEmpty) {
                return const _Message(
                  icon: Icons.info_outline,
                  title: 'No sign-in providers configured',
                  detail:
                      'Reads stay open without an account. To enable interaction, an '
                      'administrator must configure at least one OAuth provider '
                      '(Google / Apple / Facebook / X). Dev note: set the provider '
                      'client id/secret in the API settings, then reopen this screen.',
                );
              }
              return SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'Pick a provider to continue',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 24),
                    for (final p in providers)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        child: FilledButton.icon(
                          key: Key('provider-${p.name}'),
                          onPressed: _busyProvider == null ? () => _signIn(p) : null,
                          icon: _busyProvider == p.name
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.login),
                          label: Text('Continue with ${p.label}'),
                        ),
                      ),
                    if (_error != null) ...[
                      const SizedBox(height: 16),
                      Text(
                        _error!,
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Theme.of(context).colorScheme.error),
                      ),
                    ],
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({required this.icon, required this.title, required this.detail});
  final IconData icon;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 48, color: Theme.of(context).colorScheme.primary),
          const SizedBox(height: 16),
          Text(
            title,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Text(
            detail,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
