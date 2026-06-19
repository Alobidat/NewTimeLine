/// A small generic widget that fetches [fetch] on init, re-polls on [interval], and shows
/// loading / error / data states with a manual refresh. Keeps screens declarative.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/admin_client.dart';

class PollingBuilder<T> extends StatefulWidget {
  const PollingBuilder({
    super.key,
    required this.fetch,
    required this.builder,
    required this.interval,
  });

  final Future<T> Function() fetch;
  final Widget Function(BuildContext context, T data) builder;
  final Duration interval;

  @override
  State<PollingBuilder<T>> createState() => _PollingBuilderState<T>();
}

class _PollingBuilderState<T> extends State<PollingBuilder<T>> {
  Timer? _timer;
  T? _data;
  Object? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(widget.interval, (_) => _load(silent: true));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent) setState(() => _loading = true);
    try {
      final data = await widget.fetch();
      if (!mounted) return;
      setState(() {
        _data = data;
        _error = null;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading && _data == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null && _data == null) {
      return _ErrorState(error: _error!, onRetry: _load);
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: widget.builder(context, _data as T),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.error, required this.onRetry});
  final Object error;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    final msg = error is ApiException ? (error as ApiException).message : error.toString();
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 40),
            const SizedBox(height: 12),
            Text('Could not reach the Admin API', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            Text(msg, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.tonal(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
