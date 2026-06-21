/// Email-verification screen (Phase 4-G, ADR-0026): when the signed-in user's email is
/// unverified (e.g. a provider that doesn't assert a verified email), interaction is gated
/// until they confirm. Reads stay open. Flow: request a code (`/auth/verify/request`) →
/// enter it → confirm (`/auth/verify/confirm`) → [AuthState.refresh] flips
/// [AuthState.emailVerified].
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../state/auth_state.dart';

class VerifyEmailScreen extends StatefulWidget {
  const VerifyEmailScreen({super.key, required this.api, required this.auth});

  final ApiClient api;
  final AuthState auth;

  @override
  State<VerifyEmailScreen> createState() => _VerifyEmailScreenState();
}

class _VerifyEmailScreenState extends State<VerifyEmailScreen> {
  final _codeCtl = TextEditingController();
  bool _requested = false;
  bool _busy = false;
  String? _error;
  String? _info;

  @override
  void dispose() {
    _codeCtl.dispose();
    super.dispose();
  }

  Future<void> _requestCode() async {
    setState(() {
      _busy = true;
      _error = null;
      _info = null;
    });
    try {
      await widget.api.requestEmailVerify(email: widget.auth.user?.email);
      if (mounted) {
        setState(() {
          _requested = true;
          _info = 'We sent a verification code to your email.';
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not send a code: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _confirm() async {
    final code = _codeCtl.text.trim();
    if (code.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.confirmEmailVerify(code);
      await widget.auth.refresh();
      if (!mounted) return;
      if (widget.auth.emailVerified) {
        Navigator.of(context).pop(true);
      } else {
        setState(() => _error = 'That code did not verify your email. Try again.');
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Verification failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final email = widget.auth.user?.email;
    return Scaffold(
      appBar: AppBar(title: const Text('Verify your email')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Email verification is required before you can interact. Reads stay open.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (email != null) ...[
              const SizedBox(height: 8),
              Text(email, style: Theme.of(context).textTheme.labelLarge),
            ],
            const SizedBox(height: 24),
            FilledButton.icon(
              key: const Key('request-code'),
              onPressed: _busy ? null : _requestCode,
              icon: const Icon(Icons.mail_outline),
              label: Text(_requested ? 'Resend code' : 'Send verification code'),
            ),
            if (_requested) ...[
              const SizedBox(height: 24),
              TextField(
                key: const Key('verify-code-field'),
                controller: _codeCtl,
                decoration: const InputDecoration(
                  labelText: 'Verification code',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              FilledButton(
                key: const Key('confirm-code'),
                onPressed: _busy ? null : _confirm,
                child: _busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Confirm'),
              ),
            ],
            if (_info != null) ...[
              const SizedBox(height: 16),
              Text(_info!, style: TextStyle(color: Theme.of(context).colorScheme.primary)),
            ],
            if (_error != null) ...[
              const SizedBox(height: 16),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
          ],
        ),
      ),
    );
  }
}
