/// Threaded comments for an event (ADR-0025 §2.1). Fetches the flat, oldest-first list
/// from the API and builds the reply **tree** client-side (children grouped by
/// `parent_id`). Renders:
///   • a top-level composer,
///   • the comment tree (replies indented one step per depth),
///   • per-comment reply / edit / delete affordances and inline composers.
///
/// Writes resolve a server-side actor stub (no user id sent); auth arrives in Phase 4 with
/// no change here. Because there is no signed-in identity yet, edit/delete are offered on
/// every comment (the server authorizes); the UI reconciles to the server's response.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import 'detail_widgets.dart';
import 'comment_tile.dart';

class CommentsSection extends StatefulWidget {
  const CommentsSection({super.key, required this.api, required this.eventId});

  final ApiClient api;
  final String eventId;

  @override
  State<CommentsSection> createState() => _CommentsSectionState();
}

class _CommentsSectionState extends State<CommentsSection> {
  Future<List<CommentRead>>? _future;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  @override
  void didUpdateWidget(CommentsSection old) {
    super.didUpdateWidget(old);
    if (old.eventId != widget.eventId) _reload();
  }

  void _reload() {
    setState(() {
      _future = widget.api.comments(widget.eventId);
    });
  }

  Future<void> _post(String body, {String? parentId}) async {
    await widget.api.addComment(widget.eventId, body, parentId: parentId);
    _reload();
  }

  Future<void> _edit(String commentId, String body) async {
    await widget.api.editComment(widget.eventId, commentId, body);
    _reload();
  }

  Future<void> _delete(String commentId) async {
    await widget.api.deleteComment(widget.eventId, commentId);
    _reload();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Section('Discussion'),
        const SizedBox(height: 8),
        // Top-level composer.
        CommentComposer(
          key: const Key('comment-composer-root'),
          hint: 'Add a comment…',
          onSubmit: (body) => _post(body),
        ),
        const SizedBox(height: 12),
        FutureBuilder<List<CommentRead>>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState != ConnectionState.done) {
              return const Padding(
                padding: EdgeInsets.symmetric(vertical: 16),
                child: Center(child: CircularProgressIndicator()),
              );
            }
            if (snap.hasError) {
              return const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text('Could not load comments.'),
              );
            }
            final comments = snap.data ?? const <CommentRead>[];
            final roots = buildCommentTree(comments);
            if (roots.isEmpty) {
              return const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text('No comments yet — start the discussion.'),
              );
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final node in roots)
                  CommentTile(
                    node: node,
                    depth: 0,
                    onReply: (parentId, body) =>
                        _post(body, parentId: parentId),
                    onEdit: _edit,
                    onDelete: _delete,
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

/// A comment plus its (recursively built) replies, ready to render as a tree.
class CommentNode {
  CommentNode(this.comment, this.replies);
  final CommentRead comment;
  final List<CommentNode> replies;
}

/// Build the reply tree from a flat, oldest-first comment list. Children are grouped by
/// `parent_id` and kept in arrival order; orphan replies (missing parent) are surfaced at
/// the root so nothing is silently dropped. Pure + exposed for tests.
List<CommentNode> buildCommentTree(List<CommentRead> comments) {
  final nodes = {for (final c in comments) c.id: CommentNode(c, [])};
  final roots = <CommentNode>[];
  for (final c in comments) {
    final node = nodes[c.id]!;
    final parent = c.parentId == null ? null : nodes[c.parentId];
    if (parent == null) {
      roots.add(node);
    } else {
      parent.replies.add(node);
    }
  }
  return roots;
}

/// A single-field composer used both at the root and inline for replies/edits. Submits the
/// trimmed body (no-op when empty) and clears itself; the host reloads on success.
class CommentComposer extends StatefulWidget {
  const CommentComposer({
    super.key,
    required this.hint,
    required this.onSubmit,
    this.initialText,
    this.submitLabel = 'Post',
    this.autofocus = false,
    this.onCancel,
  });

  final String hint;
  final String? initialText;
  final String submitLabel;
  final bool autofocus;
  final Future<void> Function(String body) onSubmit;
  final VoidCallback? onCancel;

  @override
  State<CommentComposer> createState() => _CommentComposerState();
}

class _CommentComposerState extends State<CommentComposer> {
  late final TextEditingController _ctrl =
      TextEditingController(text: widget.initialText);
  bool _busy = false;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final body = _ctrl.text.trim();
    if (body.isEmpty || _busy) return;
    setState(() => _busy = true);
    try {
      await widget.onSubmit(body);
      if (mounted) _ctrl.clear();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.maybeOf(context)?.showSnackBar(
          const SnackBar(content: Text('Could not post your comment.')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        TextField(
          controller: _ctrl,
          autofocus: widget.autofocus,
          minLines: 1,
          maxLines: 6,
          enabled: !_busy,
          decoration: InputDecoration(
            hintText: widget.hint,
            isDense: true,
            border: const OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 6),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            if (widget.onCancel != null)
              TextButton(
                onPressed: _busy ? null : widget.onCancel,
                child: const Text('Cancel'),
              ),
            const SizedBox(width: 4),
            FilledButton(
              onPressed: _busy ? null : _submit,
              child: Text(widget.submitLabel),
            ),
          ],
        ),
      ],
    );
  }
}

/// Format a comment timestamp compactly (re-used by [CommentTile]).
String formatCommentTime(DateTime t) => formatDate(t.toLocal());
