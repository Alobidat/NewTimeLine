/// Agreement consent screen (Phase 4-G, ADR-0026): after first sign-in (or when the version
/// changes) the user must accept the versioned Terms / acceptable-use / privacy document
/// before they can interact. Acceptance posts to `/auth/agreement/accept`; interaction is
/// gated on a current acceptance ([AuthState.agreementAccepted]).
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../state/auth_state.dart';

class AgreementScreen extends StatefulWidget {
  const AgreementScreen({super.key, required this.api, required this.auth});

  final ApiClient api;
  final AuthState auth;

  @override
  State<AgreementScreen> createState() => _AgreementScreenState();
}

class _AgreementScreenState extends State<AgreementScreen> {
  late Future<Agreement> _agreement;
  bool _accepting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _agreement = widget.api.agreement();
  }

  Future<void> _accept(Agreement agreement) async {
    setState(() {
      _accepting = true;
      _error = null;
    });
    try {
      await widget.api.acceptAgreement(agreement.version);
      widget.auth.markAgreementAccepted();
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) {
        setState(() {
          _accepting = false;
          _error = 'Could not record acceptance: $e';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Terms & privacy'),
        automaticallyImplyLeading: false,
      ),
      body: FutureBuilder<Agreement>(
        future: _agreement,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('Could not load the agreement: ${snap.error}'));
          }
          final a = snap.data!;
          return Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Before you can react, comment, promote, follow, or upload, please '
                  'accept our Terms, acceptable-use policy, and privacy notice.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 12),
                Text('Version ${a.version}',
                    style: Theme.of(context).textTheme.labelMedium),
                const SizedBox(height: 16),
                if (a.summary != null)
                  Expanded(
                    child: SingleChildScrollView(
                      child: Text(a.summary!),
                    ),
                  )
                else
                  const Spacer(),
                if (a.url != null)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      onPressed: () =>
                          Clipboard.setData(ClipboardData(text: a.url!)),
                      icon: const Icon(Icons.open_in_new, size: 16),
                      // url_launcher is not a dep; copy the link so the user can open it.
                      label: const Text('Copy full document link'),
                    ),
                  ),
                if (_error != null) ...[
                  const SizedBox(height: 8),
                  Text(_error!,
                      style: TextStyle(color: Theme.of(context).colorScheme.error)),
                ],
                const SizedBox(height: 16),
                Row(
                  children: [
                    TextButton(
                      onPressed: _accepting
                          ? null
                          : () => Navigator.of(context).pop(false),
                      child: const Text('Not now'),
                    ),
                    const Spacer(),
                    FilledButton(
                      key: const Key('accept-agreement'),
                      onPressed: _accepting ? null : () => _accept(a),
                      child: _accepting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Accept & continue'),
                    ),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
