/// Upload a clip as a new event (Phase 4 IU2, ADR-0029 / social-and-feed §3).
///
/// User-generated events must satisfy the ADR-0020 metadata-complete invariant — a **time**,
/// a **location**, at least one **actor**, and at least one **linked event** — so this form
/// collects all four plus the clip itself. There is no file-picker dependency yet, so the
/// clip is supplied as a **source URL** the server fetches (the `source_url` path); a native
/// picker can later fill `fileBytes` instead without changing this screen's contract.
///
/// The submit is **interaction-gated**: an anonymous tap walks the user through sign-in →
/// consent → verify (`ensureCanInteract`) before the upload runs. On success the event lands
/// `pending` moderation, so the screen tells the user it will appear once reviewed.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../auth/interaction_gate.dart';
import '../state/auth_state.dart';

class UploadScreen extends StatefulWidget {
  const UploadScreen({super.key, required this.api, required this.auth});

  final ApiClient api;
  final AuthState auth;

  @override
  State<UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<UploadScreen> {
  final _formKey = GlobalKey<FormState>();
  final _title = TextEditingController();
  final _year = TextEditingController();
  final _location = TextEditingController();
  final _actors = TextEditingController();
  final _links = TextEditingController();
  final _sourceUrl = TextEditingController();

  String _audience = 'public'; // who can see this post
  bool _busy = false;

  @override
  void dispose() {
    _title.dispose();
    _year.dispose();
    _location.dispose();
    _actors.dispose();
    _links.dispose();
    _sourceUrl.dispose();
    super.dispose();
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  List<String> _csv(String raw) => raw
      .split(RegExp(r'[,\n]'))
      .map((s) => s.trim())
      .where((s) => s.isNotEmpty)
      .toList();

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    // Gate first so an anonymous user signs in before we attempt the write.
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    if (!mounted) return;

    setState(() => _busy = true);
    try {
      final result = await widget.api.upload(
        title: _title.text.trim(),
        tStart: double.parse(_year.text.trim()),
        geoLabel: _location.text.trim(),
        actorNames: _csv(_actors.text),
        linkEventIds: _csv(_links.text),
        sourceUrl: _sourceUrl.text.trim(),
        audience: _audience,
      );
      if (!mounted) return;
      _snack(result.isPending
          ? 'Uploaded — pending review. It will appear once approved.'
          : 'Uploaded.');
      Navigator.of(context).pop(true);
    } catch (e) {
      _snack('Upload failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Upload a clip')),
      body: AbsorbPointer(
        absorbing: _busy,
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const Text(
                'Every event needs a time, a place, who was involved, and at least one '
                'related event it connects to.',
              ),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('upload-title'),
                controller: _title,
                decoration: const InputDecoration(
                  labelText: 'Title',
                  border: OutlineInputBorder(),
                ),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'A title is required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                key: const Key('upload-year'),
                controller: _year,
                keyboardType: const TextInputType.numberWithOptions(signed: true),
                decoration: const InputDecoration(
                  labelText: 'Year (negative for BCE, e.g. -753)',
                  border: OutlineInputBorder(),
                ),
                validator: (v) {
                  if (v == null || v.trim().isEmpty) return 'A year is required';
                  return double.tryParse(v.trim()) == null ? 'Enter a number' : null;
                },
              ),
              const SizedBox(height: 12),
              TextFormField(
                key: const Key('upload-location'),
                controller: _location,
                decoration: const InputDecoration(
                  labelText: 'Location (place or country)',
                  border: OutlineInputBorder(),
                ),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'A location is required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                key: const Key('upload-actors'),
                controller: _actors,
                decoration: const InputDecoration(
                  labelText: 'Actors (comma-separated)',
                  helperText: 'Who was involved — people, groups, countries',
                  border: OutlineInputBorder(),
                ),
                validator: (v) =>
                    _csv(v ?? '').isEmpty ? 'At least one actor is required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                key: const Key('upload-links'),
                controller: _links,
                decoration: const InputDecoration(
                  labelText: 'Related event IDs (comma-separated)',
                  helperText: 'Event IDs this clip connects to',
                  border: OutlineInputBorder(),
                ),
                validator: (v) => _csv(v ?? '').isEmpty
                    ? 'Link at least one related event'
                    : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                key: const Key('upload-source-url'),
                controller: _sourceUrl,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'Clip URL',
                  helperText: 'A direct link to the video file (mp4/webm)',
                  border: OutlineInputBorder(),
                ),
                validator: (v) {
                  final s = v?.trim() ?? '';
                  if (s.isEmpty) return 'A clip URL is required';
                  final uri = Uri.tryParse(s);
                  return (uri != null && uri.hasScheme) ? null : 'Enter a valid URL';
                },
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                key: const Key('upload-audience'),
                initialValue: _audience,
                decoration: const InputDecoration(
                  labelText: 'Who can see this',
                  prefixIcon: Icon(Icons.visibility_outlined),
                  border: OutlineInputBorder(),
                ),
                items: const [
                  DropdownMenuItem(value: 'public', child: Text('Public — everyone')),
                  DropdownMenuItem(value: 'followers', child: Text('Followers')),
                  DropdownMenuItem(value: 'friends', child: Text('Friends only')),
                ],
                onChanged: (v) => setState(() => _audience = v ?? 'public'),
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                key: const Key('upload-submit'),
                onPressed: _busy ? null : _submit,
                icon: _busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.cloud_upload_outlined),
                label: Text(_busy ? 'Uploading…' : 'Upload'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
