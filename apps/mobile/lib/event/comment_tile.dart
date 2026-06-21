/// One node in the comment tree: a comment row plus its indented replies (ADR-0025 §2.1).
/// Replies are indented one step per [depth]. Each row carries reply / edit / delete
/// affordances; tapping one swaps in an inline [CommentComposer]. Soft-removed comments
/// render as a tombstone so their reply threads don't collapse.
library;

import 'package:flutter/material.dart';

import '../api/models.dart';
import 'comments_section.dart';

/// Pixels of indent applied per reply depth. Capped so deep threads stay readable.
const double kReplyIndent = 16;
const int kMaxIndentDepth = 6;

class CommentTile extends StatefulWidget {
  const CommentTile({
    super.key,
    required this.node,
    required this.depth,
    required this.onReply,
    required this.onEdit,
    required this.onDelete,
  });

  final CommentNode node;
  final int depth;
  final Future<void> Function(String parentId, String body) onReply;
  final Future<void> Function(String commentId, String body) onEdit;
  final Future<void> Function(String commentId) onDelete;

  @override
  State<CommentTile> createState() => _CommentTileState();
}

class _CommentTileState extends State<CommentTile> {
  bool _replying = false;
  bool _editing = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final c = widget.node.comment;
    final indent =
        kReplyIndent * widget.depth.clamp(0, kMaxIndentDepth).toDouble();

    return Padding(
      padding: EdgeInsets.only(left: indent, bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // The comment body (or a tombstone for soft-removed comments).
          if (c.isRemoved)
            Text(
              '[comment removed]',
              style: theme.textTheme.bodyMedium?.copyWith(
                fontStyle: FontStyle.italic,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            )
          else if (_editing)
            CommentComposer(
              key: Key('comment-edit-${c.id}'),
              hint: 'Edit your comment…',
              initialText: c.body,
              submitLabel: 'Save',
              autofocus: true,
              onCancel: () => setState(() => _editing = false),
              onSubmit: (body) async {
                await widget.onEdit(c.id, body);
                if (mounted) setState(() => _editing = false);
              },
            )
          else
            _CommentBody(comment: c),

          // Affordances (hidden while editing or on a tombstone).
          if (!c.isRemoved && !_editing)
            Wrap(
              spacing: 4,
              children: [
                _MiniAction(
                  label: 'Reply',
                  onTap: () => setState(() => _replying = !_replying),
                ),
                _MiniAction(
                  label: 'Edit',
                  onTap: () => setState(() => _editing = true),
                ),
                _MiniAction(
                  label: 'Delete',
                  onTap: () => _confirmDelete(context, c.id),
                ),
              ],
            ),

          // Inline reply composer.
          if (_replying)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: CommentComposer(
                key: Key('comment-reply-${c.id}'),
                hint: 'Write a reply…',
                submitLabel: 'Reply',
                autofocus: true,
                onCancel: () => setState(() => _replying = false),
                onSubmit: (body) async {
                  await widget.onReply(c.id, body);
                  if (mounted) setState(() => _replying = false);
                },
              ),
            ),

          // Replies, recursively, indented one more step.
          for (final child in widget.node.replies)
            CommentTile(
              node: child,
              depth: widget.depth + 1,
              onReply: widget.onReply,
              onEdit: widget.onEdit,
              onDelete: widget.onDelete,
            ),
        ],
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context, String id) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete comment?'),
        content: const Text('This removes the comment but keeps its replies.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok == true) await widget.onDelete(id);
  }
}

class _CommentBody extends StatelessWidget {
  const _CommentBody({required this.comment});
  final CommentRead comment;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(Icons.account_circle,
                size: 18, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(width: 6),
            Text(
              formatCommentTime(comment.createdAt),
              style: theme.textTheme.labelSmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            if (comment.updatedAt.isAfter(comment.createdAt)) ...[
              const SizedBox(width: 6),
              Text('(edited)',
                  style: theme.textTheme.labelSmall
                      ?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
            ],
          ],
        ),
        const SizedBox(height: 2),
        Text(comment.body, style: theme.textTheme.bodyMedium),
      ],
    );
  }
}

class _MiniAction extends StatelessWidget {
  const _MiniAction({required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => TextButton(
    style: TextButton.styleFrom(
      minimumSize: const Size(0, 32),
      padding: const EdgeInsets.symmetric(horizontal: 8),
      visualDensity: VisualDensity.compact,
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    ),
    onPressed: onTap,
    child: Text(label),
  );
}
