/// The full-page discussion for an event (rich social conversation). A compact event/media
/// header (thumbnail + title + meta + summary) sits above the comprehensive, threaded comments:
/// each comment shows its author's avatar + name (tap → their profile), an emotion-reaction row
/// (the same kinds as events), and reply/edit/delete. All writes are interaction-gated.
///
/// Replaces the cramped bottom-sheet discussion: opened as its own route from the feed's
/// Comment button.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../auth/interaction_gate.dart';
import '../domain/time_format.dart';
import '../profile/avatar.dart';
import '../profile/user_profile_page.dart';
import '../state/auth_state.dart';
import '../upload/upload_screen.dart';
import 'comments_section.dart' show CommentComposer, CommentNode, buildCommentTree;
import 'media_gallery.dart' show MediaThumb, isShowableMedia, orderMediaClipsFirst;
import 'media_viewer.dart';
import 'reaction_bar.dart' show kReactionKinds;

class CommentsPage extends StatefulWidget {
  const CommentsPage({
    super.key,
    required this.api,
    required this.auth,
    required this.event,
  });

  final ApiClient api;
  final AuthState auth;
  final EventRead event;

  @override
  State<CommentsPage> createState() => _CommentsPageState();
}

class _CommentsPageState extends State<CommentsPage> {
  EventDetail? _detail;
  Future<List<CommentRead>>? _comments;

  @override
  void initState() {
    super.initState();
    _reload();
    widget.api.event(widget.event.id).then((d) {
      if (mounted) setState(() => _detail = d);
    }).catchError((_) {});
  }

  void _reload() {
    final comments = widget.api.comments(widget.event.id);
    setState(() {
      _comments = comments; // block body so setState's closure returns void, not the Future
    });
  }

  /// Gate, then run [action]; reload on success. Returns silently if the user cancels the gate.
  Future<void> _gated(Future<void> Function() action) async {
    if (!await ensureCanInteract(context, widget.api, widget.auth)) return;
    await action();
    if (mounted) _reload();
  }

  Future<void> _post(String body, {String? parentId}) =>
      _gated(() => widget.api.addComment(widget.event.id, body, parentId: parentId));

  Future<void> _edit(String id, String body) =>
      _gated(() => widget.api.editComment(widget.event.id, id, body));

  Future<void> _delete(String id) =>
      _gated(() => widget.api.deleteComment(widget.event.id, id));

  void _openProfile(String userId) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            UserProfilePage(api: widget.api, auth: widget.auth, userId: userId),
      ),
    );
  }

  /// Reply to this event with a video — opens the capture/upload flow pre-linked to it.
  void _replyWithVideo() {
    Navigator.of(context).push(
      MaterialPageRoute<bool>(
        builder: (_) => UploadScreen(
          api: widget.api,
          auth: widget.auth,
          replyToEventId: widget.event.id,
          replyToTitle: widget.event.title,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Discussion'),
        actions: [
          IconButton(
            key: const Key('discussion-reply-video'),
            icon: const Icon(Icons.video_call_outlined),
            tooltip: 'Reply with a video',
            onPressed: _replyWithVideo,
          ),
        ],
      ),
      body: Column(
        children: [
          _EventHeader(api: widget.api, event: widget.event, detail: _detail),
          const Divider(height: 1),
          Expanded(
            child: FutureBuilder<List<CommentRead>>(
              future: _comments,
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                final comments = snap.data ?? const <CommentRead>[];
                final roots = buildCommentTree(comments);
                return ListView(
                  padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
                  children: [
                    if (snap.hasError)
                      const Text('Could not load comments.')
                    else if (roots.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 24),
                        child: Center(
                          child: Text('No comments yet — start the discussion.'),
                        ),
                      ),
                    for (final node in roots)
                      RichCommentTile(
                        api: widget.api,
                        auth: widget.auth,
                        eventId: widget.event.id,
                        node: node,
                        depth: 0,
                        onReply: (parentId, body) => _post(body, parentId: parentId),
                        onEdit: _edit,
                        onDelete: _delete,
                        onOpenProfile: _openProfile,
                        gate: () => ensureCanInteract(context, widget.api, widget.auth),
                      ),
                  ],
                );
              },
            ),
          ),
          // Root composer pinned to the bottom.
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
              child: CommentComposer(
                key: const Key('comments-page-composer'),
                hint: 'Add a comment…',
                onSubmit: (body) => _post(body),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The compact event/media header above the thread: a tappable hero thumbnail (→ fullscreen),
/// the title, the time/place meta, and a short summary.
class _EventHeader extends StatelessWidget {
  const _EventHeader({required this.api, required this.event, required this.detail});
  final ApiClient api;
  final EventRead event;
  final EventDetail? detail;

  @override
  Widget build(BuildContext context) {
    final media =
        orderMediaClipsFirst((detail?.media ?? const []).where(isShowableMedia).toList());
    final hero = media.isNotEmpty ? media.first : null;
    final meta = [
      formatLabel(event.tStart, event.precision, instant: event.instant),
      if (event.geoLabel != null) event.geoLabel!,
      if (event.category != null) event.category!,
    ].join('  ·  ');

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (hero != null)
            GestureDetector(
              onTap: () => openMediaViewer(context, api, media, 0),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: SizedBox(
                  width: 84,
                  height: 84,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      MediaThumb(api: api, media: hero, hero: false),
                      if (hero.kind == 'video')
                        const Center(
                          child: Icon(Icons.play_circle_fill,
                              color: Colors.white70, size: 30),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          if (hero != null) const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(event.title,
                    style: Theme.of(context).textTheme.titleMedium,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis),
                const SizedBox(height: 4),
                Text(meta,
                    style: Theme.of(context).textTheme.bodySmall,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
                if (event.summary != null) ...[
                  const SizedBox(height: 6),
                  Text(event.summary!,
                      style: Theme.of(context).textTheme.bodySmall,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// A single threaded comment with avatar, author (→ profile), body, an emotion-reaction row,
/// and reply/edit/delete. Renders its replies recursively, indented one step per [depth].
class RichCommentTile extends StatefulWidget {
  const RichCommentTile({
    super.key,
    required this.api,
    required this.auth,
    required this.eventId,
    required this.node,
    required this.depth,
    required this.onReply,
    required this.onEdit,
    required this.onDelete,
    required this.onOpenProfile,
    required this.gate,
  });

  final ApiClient api;
  final AuthState auth;
  final String eventId;
  final CommentNode node;
  final int depth;
  final Future<void> Function(String parentId, String body) onReply;
  final Future<void> Function(String commentId, String body) onEdit;
  final Future<void> Function(String commentId) onDelete;
  final void Function(String userId) onOpenProfile;
  final Future<bool> Function() gate;

  @override
  State<RichCommentTile> createState() => _RichCommentTileState();
}

class _RichCommentTileState extends State<RichCommentTile> {
  static const double _indentPerDepth = 16;
  static const double _maxIndent = 48;

  bool _replying = false;
  bool _editing = false;

  // Per-comment reaction state, seeded from the server payload and updated optimistically.
  late Map<String, int> _counts = Map.of(widget.node.comment.reactions);
  late Set<String> _mine = widget.node.comment.myReactions.toSet();
  final Set<String> _inFlight = {};

  Future<void> _toggleReaction(String kind) async {
    if (_inFlight.contains(kind)) return;
    if (!await widget.gate()) return;
    final wasMine = _mine.contains(kind);
    setState(() {
      _inFlight.add(kind);
      _counts[kind] = ((_counts[kind] ?? 0) + (wasMine ? -1 : 1)).clamp(0, 1 << 30);
      wasMine ? _mine.remove(kind) : _mine.add(kind);
    });
    try {
      final fresh =
          await widget.api.toggleCommentReaction(widget.eventId, widget.node.comment.id, kind);
      if (mounted) {
        setState(() {
          _counts = Map.of(fresh.counts);
          _mine = Set.of(fresh.mine);
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          // roll back
          _counts[kind] = ((_counts[kind] ?? 0) + (wasMine ? 1 : -1)).clamp(0, 1 << 30);
          wasMine ? _mine.add(kind) : _mine.remove(kind);
        });
      }
    } finally {
      if (mounted) setState(() => _inFlight.remove(kind));
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.node.comment;
    final indent = (widget.depth * _indentPerDepth).clamp(0, _maxIndent).toDouble();
    final author = c.author;
    final theme = Theme.of(context);

    return Padding(
      padding: EdgeInsets.only(left: indent, top: 6, bottom: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              GestureDetector(
                onTap: author != null ? () => widget.onOpenProfile(author.id) : null,
                child: Avatar(
                  label: author?.label ?? '?',
                  url: author?.avatarUrl,
                  radius: 16,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        GestureDetector(
                          onTap: author != null
                              ? () => widget.onOpenProfile(author.id)
                              : null,
                          child: Text(
                            author?.label ?? 'User',
                            style: theme.textTheme.labelLarge
                                ?.copyWith(fontWeight: FontWeight.w600),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(formatDate(c.createdAt.toLocal()),
                            style: theme.textTheme.bodySmall
                                ?.copyWith(color: theme.colorScheme.outline)),
                      ],
                    ),
                    const SizedBox(height: 2),
                    if (c.isRemoved)
                      Text('[removed]',
                          style: theme.textTheme.bodyMedium
                              ?.copyWith(fontStyle: FontStyle.italic, color: theme.colorScheme.outline))
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
                      Text(c.body, style: theme.textTheme.bodyMedium),
                    if (!c.isRemoved && !_editing) _reactionRow(),
                    if (!c.isRemoved && !_editing) _actionRow(),
                    if (_replying)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: CommentComposer(
                          key: Key('comment-reply-${c.id}'),
                          hint: 'Reply…',
                          submitLabel: 'Reply',
                          autofocus: true,
                          onCancel: () => setState(() => _replying = false),
                          onSubmit: (body) async {
                            await widget.onReply(c.id, body);
                            if (mounted) setState(() => _replying = false);
                          },
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
          // Replies, recursively.
          for (final reply in widget.node.replies)
            RichCommentTile(
              api: widget.api,
              auth: widget.auth,
              eventId: widget.eventId,
              node: reply,
              depth: widget.depth + 1,
              onReply: widget.onReply,
              onEdit: widget.onEdit,
              onDelete: widget.onDelete,
              onOpenProfile: widget.onOpenProfile,
              gate: widget.gate,
            ),
        ],
      ),
    );
  }

  Widget _reactionRow() {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Wrap(
        spacing: 4,
        children: [
          for (final kind in kReactionKinds.keys)
            _MiniReaction(
              kind: kind,
              count: _counts[kind] ?? 0,
              active: _mine.contains(kind),
              onTap: () => _toggleReaction(kind),
            ),
        ],
      ),
    );
  }

  Widget _actionRow() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _LinkAction(label: 'Reply', onTap: () => setState(() => _replying = !_replying)),
        _LinkAction(label: 'Edit', onTap: () => setState(() => _editing = true)),
        _LinkAction(label: 'Delete', onTap: () => widget.onDelete(widget.node.comment.id)),
      ],
    );
  }
}

/// A compact emotion toggle for a comment (icon + count). Active when the caller set it.
class _MiniReaction extends StatelessWidget {
  const _MiniReaction({
    required this.kind,
    required this.count,
    required this.active,
    required this.onTap,
  });
  final String kind;
  final int count;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final meta = kReactionKinds[kind]!;
    final color =
        active ? Theme.of(context).colorScheme.primary : Theme.of(context).colorScheme.outline;
    return InkWell(
      key: Key('comment-reaction-$kind'),
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(active ? meta.iconActive : meta.icon, size: 15, color: color),
            if (count > 0) ...[
              const SizedBox(width: 3),
              Text('$count', style: TextStyle(fontSize: 12, color: color)),
            ],
          ],
        ),
      ),
    );
  }
}

class _LinkAction extends StatelessWidget {
  const _LinkAction({required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onTap,
      style: TextButton.styleFrom(
        minimumSize: const Size(0, 32),
        padding: const EdgeInsets.symmetric(horizontal: 8),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      child: Text(label, style: const TextStyle(fontSize: 12)),
    );
  }
}
