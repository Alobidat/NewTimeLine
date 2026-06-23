/// Sign-in screen (Phase 4-G, ADR-0026): lists the backend's config-driven OAuth providers
/// as buttons (tapping one runs the OAuth2/OIDC auth-code+PKCE flow) AND — when the backend
/// enables it — offers a self-contained **email-code** sign-in (no external provider). On
/// success the session JWT is adopted by [AuthState] and `/account/me` is fetched.
///
/// Both paths are config-driven and may be absent. With neither available the screen renders
/// a clear "no sign-in configured" note rather than a broken/empty list.
///
/// Flow handoff: the OAuth browser launch + callback handling lives in [runOAuthFlow]
/// (`oauth_flow.dart`); the email-code flow is a two-step form (send code → enter code) backed
/// by [ApiClient.devLoginStart] / [ApiClient.devLoginVerify].
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../state/auth_state.dart';
import 'oauth_flow.dart';
import 'web_oauth.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.api, required this.auth});

  final ApiClient api;
  final AuthState auth;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  late Future<AuthOptions> _options;
  String? _busyProvider;
  String? _error;

  @override
  void initState() {
    super.initState();
    _options = widget.api.authOptions();
  }

  Future<void> _signIn(AuthProvider provider) async {
    setState(() {
      _busyProvider = provider.name;
      _error = null;
    });
    try {
      // Web: a real full-page redirect to the provider. We stash the PKCE material, navigate
      // away, and the app completes the exchange on the return load (see main.dart). The code
      // below does not return — the page unloads.
      if (isWebPlatform) {
        final redirectUri = webRedirectUri();
        final challenge =
            await widget.api.loginChallenge(provider.name, redirectUri: redirectUri);
        stashOAuth(
          provider: provider.name,
          state: challenge.state ?? '',
          codeVerifier: challenge.codeVerifier ?? '',
          redirectUri: redirectUri,
        );
        redirectToAuthorize(challenge.authorizeUrl);
        return;
      }
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
          child: FutureBuilder<AuthOptions>(
            future: _options,
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
              final options = snap.data ?? AuthOptions(providers: const []);
              final providers = options.providers;
              if (providers.isEmpty && !options.devLogin) {
                return const _Message(
                  icon: Icons.info_outline,
                  title: 'No sign-in configured',
                  detail:
                      'Reads stay open without an account. To enable interaction, an '
                      'administrator must configure at least one OAuth provider '
                      '(Google / Apple / Facebook / X) or enable the email-code login.',
                );
              }
              return SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (providers.isNotEmpty) ...[
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
                            onPressed:
                                _busyProvider == null ? () => _signIn(p) : null,
                            icon: _busyProvider == p.name
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child:
                                        CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : const Icon(Icons.login),
                            label: Text('Continue with ${p.label}'),
                          ),
                        ),
                    ],
                    if (providers.isNotEmpty && options.devLogin) ...[
                      const SizedBox(height: 20),
                      Row(
                        children: [
                          const Expanded(child: Divider()),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 12),
                            child: Text(
                              'or',
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ),
                          const Expanded(child: Divider()),
                        ],
                      ),
                      const SizedBox(height: 8),
                    ],
                    if (options.devLogin)
                      _EmailCodeLogin(
                        api: widget.api,
                        auth: widget.auth,
                        onSignedIn: () => Navigator.of(context).pop(true),
                      ),
                    if (_error != null) ...[
                      const SizedBox(height: 16),
                      Text(
                        _error!,
                        textAlign: TextAlign.center,
                        style:
                            TextStyle(color: Theme.of(context).colorScheme.error),
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

/// The self-contained email-code sign-in form: enter an email → "Send code" → enter the code
/// → "Sign in". In non-prod the backend echoes the code, which we prefill for convenience.
class _EmailCodeLogin extends StatefulWidget {
  const _EmailCodeLogin({
    required this.api,
    required this.auth,
    required this.onSignedIn,
  });
  final ApiClient api;
  final AuthState auth;
  final VoidCallback onSignedIn;

  @override
  State<_EmailCodeLogin> createState() => _EmailCodeLoginState();
}

class _EmailCodeLoginState extends State<_EmailCodeLogin> {
  final _email = TextEditingController();
  final _code = TextEditingController();
  bool _codeSent = false;
  bool _busy = false;
  String? _info;
  String? _error;

  bool get _validEmail => _email.text.contains('@');

  Future<void> _sendCode() async {
    if (!_validEmail) {
      setState(() => _error = 'Enter a valid email address.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _info = null;
    });
    try {
      final res = await widget.api.devLoginStart(_email.text.trim());
      if (!mounted) return;
      setState(() {
        _codeSent = true;
        if (res.devCode != null) {
          _code.text = res.devCode!;
          _info = 'Dev mode: code prefilled. Tap "Sign in".';
        } else {
          _info = 'We emailed a sign-in code to ${_email.text.trim()}.';
        }
      });
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not send code: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verify() async {
    if (_code.text.trim().isEmpty) {
      setState(() => _error = 'Enter the code from your email.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final session = await widget.api.devLoginVerify(
        _email.text.trim(),
        _code.text.trim(),
      );
      await widget.auth.adopt(session);
      if (mounted) widget.onSignedIn();
    } catch (e) {
      if (mounted) setState(() => _error = 'Sign-in failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _email.dispose();
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          'Sign in with email',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('email-login-field'),
          controller: _email,
          enabled: !_busy,
          keyboardType: TextInputType.emailAddress,
          autofillHints: const [AutofillHints.email],
          decoration: const InputDecoration(
            labelText: 'Email',
            prefixIcon: Icon(Icons.alternate_email),
          ),
          onChanged: (_) => setState(() {}),
        ),
        if (_codeSent) ...[
          const SizedBox(height: 10),
          TextField(
            key: const Key('email-code-field'),
            controller: _code,
            enabled: !_busy,
            decoration: const InputDecoration(
              labelText: 'Sign-in code',
              prefixIcon: Icon(Icons.pin),
            ),
          ),
        ],
        const SizedBox(height: 12),
        if (!_codeSent)
          FilledButton.icon(
            key: const Key('email-send-code'),
            onPressed: _busy ? null : _sendCode,
            icon: _busy
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.mail_outline),
            label: const Text('Send code'),
          )
        else
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  key: const Key('email-verify'),
                  onPressed: _busy ? null : _verify,
                  icon: _busy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.login),
                  label: const Text('Sign in'),
                ),
              ),
              const SizedBox(width: 8),
              TextButton(
                onPressed: _busy ? null : _sendCode,
                child: const Text('Resend'),
              ),
            ],
          ),
        if (_info != null) ...[
          const SizedBox(height: 10),
          Text(
            _info!,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
        if (_error != null) ...[
          const SizedBox(height: 10),
          Text(
            _error!,
            textAlign: TextAlign.center,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
      ],
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
