/// The ONE standard event article layout (ADR-0021), shared by the modal sheet and the
/// inline side panel so they never diverge. Renders, in order:
///
///   Title → Media (hero + gallery) → Summary → Subject/body (with inline links to
///   related events the body names) → Actors & place (entity chips) → Related events
///   footer ("What led to this" / "What this caused" / "Same place / same actors") →
///   Sources → sub-timeline references.
///
/// The related-events footer is the product's second-most-important element (ADR-0021):
/// it is ALWAYS shown, drawing on `/events/{id}/related` + `/chain`. Inline body links
/// and the footer together give the user the full historical picture.
///
/// The article fetches its own related/chain data; the host (sheet/panel) supplies the
/// already-loaded [EventDetail], an optional [onSelectRelated] (panel pivots in place;
/// sheet falls back to opening a fresh detail), an optional [onSelectEntity] pivot, and
/// optional [headerTrailing]/[footerExtra] slots for host-specific affordances (the
/// panel's close button, the sheet's "Dig the history" button).
library;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import 'comments_section.dart';
import 'detail_widgets.dart';
import 'event_detail_sheet.dart' show showEventDetailById;
import 'link_picker.dart';
import 'reaction_bar.dart';
import 'source_vote_bar.dart';

class EventArticle extends StatefulWidget {
  const EventArticle({
    super.key,
    required this.api,
    required this.detail,
    this.scrollController,
    this.padding = const EdgeInsets.fromLTRB(20, 8, 20, 24),
    this.onSelectRelated,
    this.onSelectEntity,
    this.headerTrailing,
    this.footerExtra,
  });

  final ApiClient api;
  final EventDetail detail;

  /// Host-supplied scroll controller (the sheet drives a [DraggableScrollableSheet]).
  final ScrollController? scrollController;
  final EdgeInsets padding;

  /// Pivot to a related event. When null the article opens a fresh detail sheet itself.
  final void Function(String eventId)? onSelectRelated;

  /// Pivot to an entity's events. When null the chips are non-interactive.
  final void Function(EntityRead entity)? onSelectEntity;

  /// Slot beside the title (e.g. the panel's close button).
  final Widget? headerTrailing;

  /// Slot directly under the title meta row (e.g. the sheet's "Dig the history" button).
  final Widget? footerExtra;

  @override
  State<EventArticle> createState() => _EventArticleState();
}

class _EventArticleState extends State<EventArticle> {
  late Future<List<RelatedEvent>> _related;

  // Source-credibility votes (ADR-0025 §2.3) — one fetch per event, shared by every
  // source row's vote bar. Null while loading / on failure.
  SourceVotes? _sourceVotes;
  final Set<String> _voteInFlight = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(EventArticle old) {
    super.didUpdateWidget(old);
    if (old.detail.id != widget.detail.id) {
      _sourceVotes = null;
      _load();
    }
  }

  void _load() {
    _related = widget.api
        .related(widget.detail.id)
        .catchError((_) => <RelatedEvent>[]);
    _loadSourceVotes();
  }

  Future<void> _loadSourceVotes() async {
    try {
      final v = await widget.api.sourceVotes(widget.detail.id);
      if (mounted) setState(() => _sourceVotes = v);
    } catch (_) {
      // Leave tallies empty; the bars still render and casting can retry.
    }
  }

  /// Reload the related footer (after the user creates a link). The new edge returns
  /// tagged origin=user and renders distinctly.
  void _reloadRelated() {
    setState(() {
      _related = widget.api
          .related(widget.detail.id)
          .catchError((_) => <RelatedEvent>[]);
    });
  }

  Future<void> _castSourceVote(String sourceId, String verdict) async {
    if (_voteInFlight.contains(sourceId)) return;
    setState(() => _voteInFlight.add(sourceId));
    try {
      final fresh =
          await widget.api.castSourceVote(widget.detail.id, sourceId, verdict);
      if (mounted) setState(() => _sourceVotes = fresh);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.maybeOf(context)?.showSnackBar(
          const SnackBar(content: Text('Could not record your vote.')),
        );
      }
    } finally {
      if (mounted) setState(() => _voteInFlight.remove(sourceId));
    }
  }

  Future<void> _openLinkPicker() async {
    final created = await showLinkPicker(
      context,
      widget.api,
      srcEventId: widget.detail.id,
    );
    if (created) _reloadRelated();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = widget.detail;
    final media = e.media.where(isShowableMedia).toList();

    return ListView(
      controller: widget.scrollController,
      padding: widget.padding,
      children: [
        // 1. Title (with optional host trailing slot).
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: Text(e.title, style: theme.textTheme.titleLarge)),
            if (widget.headerTrailing != null) widget.headerTrailing!,
          ],
        ),
        const SizedBox(height: 8),
        _MetaRow(e: e),

        // Reaction bar (ADR-0025 §2.2) — near the title/meta so engagement is immediate.
        const SizedBox(height: 8),
        ReactionBar(api: widget.api, eventId: e.id),

        // 2. Media — hero (clip-preferred) + expandable gallery.
        if (media.isNotEmpty) ...[
          const SizedBox(height: 12),
          // Info/article context: show a still poster for clips (no autoplay replay); tapping
          // opens the fullscreen viewer with sound.
          MediaGallery(api: widget.api, items: media, stillHero: true),
        ],

        if (widget.footerExtra != null) ...[
          const SizedBox(height: 12),
          widget.footerExtra!,
        ],

        // 3. Summary — the short lead, given a touch more weight than body prose so the
        // eye lands on it first after the media (ADR-0024).
        if (e.summary != null && e.summary!.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text(
            e.summary!,
            style: theme.textTheme.bodyLarge?.copyWith(height: 1.4),
          ),
        ],

        // 4. Subject / body, with inline links to named related events. Long bodies are
        // collapsed behind a "Read more" expander so prose never dominates the fold.
        if (e.body != null && e.body!.isNotEmpty) ...[
          const SizedBox(height: 12),
          _ExpandableBody(
            body: e.body!,
            relatedFuture: _related,
            style: theme.textTheme.bodyMedium,
            linkColor: theme.colorScheme.primary,
            onSelect: _selectRelated,
          ),
        ],

        // 5. Actors & place.
        if (e.entities.isNotEmpty) ...[
          const SizedBox(height: 20),
          const Section('Actors & place'),
          const SizedBox(height: 4),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final er in e.entities) _entityChip(er),
            ],
          ),
        ],

        // 6. Related events footer — always present. Includes a "Link this event"
        // affordance; user-created links render distinctly (ADR-0025 §2.4).
        const SizedBox(height: 20),
        RelatedFooter(
          future: _related,
          api: widget.api,
          onSelect: _selectRelated,
          onAddLink: _openLinkPicker,
        ),

        // 7. Sources, each with a credibility-vote bar (ADR-0025 §2.3).
        const SizedBox(height: 20),
        const Section('Sources'),
        if (e.sources.isEmpty)
          const Text('No sources attached.')
        else
          ...e.sources.map(_sourceTile),

        // 8. Discussion — threaded comments (ADR-0025 §2.1).
        const SizedBox(height: 24),
        CommentsSection(api: widget.api, eventId: e.id),

        // 9. Sub-timeline references (deep-history subjects, ADR-0005).
        if (e.references.isNotEmpty) ...[
          const SizedBox(height: 12),
          const Section('Explore the history (sub-timeline)'),
          ...e.references.map(
            (r) => ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.history_edu_outlined),
              title: Text(r.label),
              subtitle: Text('${formatLabel(r.tStart, r.precision)}'
                  '${r.detail != null ? ' — ${r.detail}' : ''}'),
            ),
          ),
        ],
      ],
    );
  }

  void _selectRelated(String eventId) {
    final cb = widget.onSelectRelated;
    if (cb != null) {
      cb(eventId);
    } else {
      // No host pivot (the modal sheet): open the target in its own sheet.
      showEventDetailById(context, widget.api, eventId);
    }
  }

  Widget _entityChip(EntityRole er) {
    final label = Text('${er.entity.name} · ${er.role}');
    final avatar = Icon(entityIcon(er.entity.kind), size: 16);
    if (widget.onSelectEntity == null) {
      return Chip(
        avatar: avatar,
        label: label,
        visualDensity: VisualDensity.compact,
      );
    }
    return ActionChip(
      avatar: avatar,
      label: label,
      visualDensity: VisualDensity.compact,
      onPressed: () => widget.onSelectEntity!(er.entity),
    );
  }

  Widget _sourceTile(SourceRead s) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.article_outlined),
          title: Text(s.title ?? s.domain),
          subtitle: Text(
            [
              s.publisher ?? s.domain,
              if (s.publishedAt != null) formatDate(s.publishedAt!),
              s.url,
            ].join(' · '),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(left: 40, bottom: 4),
          child: SourceVoteBar(
            sourceId: s.id,
            votes: _sourceVotes,
            busy: _voteInFlight.contains(s.id),
            onCast: (verdict) => _castSourceVote(s.id, verdict),
          ),
        ),
      ],
    ),
  );
}

/// The pill meta row (time, place, category, severity, source count).
class _MetaRow extends StatelessWidget {
  const _MetaRow({required this.e});
  final EventDetail e;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 8,
    runSpacing: 8,
    crossAxisAlignment: WrapCrossAlignment.center,
    children: [
      Pill(formatLabel(e.tStart, e.precision, instant: e.instant),
          Icons.schedule),
      if (e.geoLabel != null) Pill(e.geoLabel!, Icons.place_outlined),
      if (e.category != null) Pill(e.category!, Icons.category_outlined),
      SeverityBadge(e.severity),
      Pill('${e.sourceCount} source(s)', Icons.link),
    ],
  );
}

/// How many characters of body prose count as "long" — past this, the body collapses
/// behind a "Read more" expander so media stays above the fold (ADR-0024). Exposed pure
/// for tests.
const int kBodyCollapseChars = 280;

bool bodyNeedsExpander(String body) => body.trim().length > kBodyCollapseChars;

/// Body paragraph that (a) turns any mention of a related event's title into a tappable
/// inline link, and (b) collapses long prose behind a "Read more" / "Show less" toggle.
/// Matching is case-insensitive on whole-title occurrences; longest titles win so nested
/// names don't double-link.
class _ExpandableBody extends StatefulWidget {
  const _ExpandableBody({
    required this.body,
    required this.relatedFuture,
    required this.style,
    required this.linkColor,
    required this.onSelect,
  });

  final String body;
  final Future<List<RelatedEvent>> relatedFuture;
  final TextStyle? style;
  final Color linkColor;
  final void Function(String eventId) onSelect;

  @override
  State<_ExpandableBody> createState() => _ExpandableBodyState();
}

class _ExpandableBodyState extends State<_ExpandableBody> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final long = bodyNeedsExpander(widget.body);
    final collapsed = long && !_expanded;

    return FutureBuilder<List<RelatedEvent>>(
      future: widget.relatedFuture,
      builder: (context, snap) {
        final related = snap.data ?? const <RelatedEvent>[];
        final spans = buildBodySpans(
          body: widget.body,
          related: related,
          linkColor: widget.linkColor,
          onSelect: widget.onSelect,
        );
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text.rich(
              TextSpan(style: widget.style, children: spans),
              maxLines: collapsed ? 4 : null,
              overflow:
                  collapsed ? TextOverflow.ellipsis : TextOverflow.clip,
            ),
            if (long)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: InkWell(
                  onTap: () => setState(() => _expanded = !_expanded),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        _expanded ? 'Show less' : 'Read more',
                        style: theme.textTheme.labelLarge
                            ?.copyWith(color: widget.linkColor),
                      ),
                      Icon(
                        _expanded
                            ? Icons.expand_less
                            : Icons.expand_more,
                        size: 18,
                        color: widget.linkColor,
                      ),
                    ],
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}

/// Build the inline-linked spans for [body]. Public + pure so it is unit-testable: any
/// related-event title that appears verbatim in the body becomes a [TextSpan] whose tap
/// recognizer fires [onSelect] with that event id. Exposed for tests.
List<InlineSpan> buildBodySpans({
  required String body,
  required List<RelatedEvent> related,
  required Color linkColor,
  required void Function(String eventId) onSelect,
}) {
  // Dedup by title, keep the longest titles first so overlaps prefer the specific name.
  final byTitle = <String, String>{}; // lower title -> event id
  for (final r in related) {
    final t = r.event.title.trim();
    if (t.isEmpty) continue;
    byTitle.putIfAbsent(t.toLowerCase(), () => r.event.id);
  }
  final titles = byTitle.keys.toList()
    ..sort((a, b) => b.length.compareTo(a.length));
  if (titles.isEmpty) {
    return [TextSpan(text: body)];
  }

  final lower = body.toLowerCase();
  // Find non-overlapping matches across the whole body.
  final matches = <_Match>[];
  final claimed = List<bool>.filled(body.length, false);
  for (final title in titles) {
    var from = 0;
    while (true) {
      final idx = lower.indexOf(title, from);
      if (idx < 0) break;
      final end = idx + title.length;
      var free = true;
      for (var i = idx; i < end; i++) {
        if (claimed[i]) {
          free = false;
          break;
        }
      }
      if (free) {
        for (var i = idx; i < end; i++) {
          claimed[i] = true;
        }
        matches.add(_Match(idx, end, byTitle[title]!));
      }
      from = end;
    }
  }
  if (matches.isEmpty) {
    return [TextSpan(text: body)];
  }
  matches.sort((a, b) => a.start.compareTo(b.start));

  final spans = <InlineSpan>[];
  final recognizers = <TapGestureRecognizer>[];
  var cursor = 0;
  for (final m in matches) {
    if (m.start > cursor) {
      spans.add(TextSpan(text: body.substring(cursor, m.start)));
    }
    final rec = TapGestureRecognizer()..onTap = () => onSelect(m.eventId);
    recognizers.add(rec);
    spans.add(TextSpan(
      text: body.substring(m.start, m.end),
      style: TextStyle(
        color: linkColor,
        decoration: TextDecoration.underline,
        decorationColor: linkColor,
      ),
      recognizer: rec,
    ));
    cursor = m.end;
  }
  if (cursor < body.length) {
    spans.add(TextSpan(text: body.substring(cursor)));
  }
  return spans;
}

class _Match {
  _Match(this.start, this.end, this.eventId);
  final int start;
  final int end;
  final String eventId;
}

/// The always-present related-events footer (ADR-0021). Splits one-hop neighbours into
/// the three product-meaningful groups:
///   • "What led to this"  — causal edges pointing back (direction == back).
///   • "What this caused"  — causal edges pointing forward (direction == forward).
///   • "Same place / same actors" — structural same-place / same-actor links.
/// Shown even while loading / empty so the section never disappears.
class RelatedFooter extends StatelessWidget {
  const RelatedFooter({
    super.key,
    required this.future,
    required this.api,
    required this.onSelect,
    this.onAddLink,
  });

  final Future<List<RelatedEvent>> future;
  final ApiClient api;
  final void Function(String eventId) onSelect;

  /// Opens the "link this event" picker (ADR-0025 §2.4). When null the affordance hides.
  final VoidCallback? onAddLink;

  static bool _isStructural(String kind) =>
      kind == 'same-place' || kind == 'same-actor';

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<RelatedEvent>>(
      future: future,
      builder: (context, snap) {
        final loading = snap.connectionState != ConnectionState.done;
        final items = snap.data ?? const <RelatedEvent>[];

        // User-asserted links surface in their own group, tagged "added by a user"
        // (ADR-0025 §2.4), regardless of direction/kind.
        final userAdded = items.where((r) => r.isUserAdded).toList();
        final agentItems = items.where((r) => !r.isUserAdded).toList();

        final ledTo = agentItems
            .where((r) => r.direction == 'back' && !_isStructural(r.kind))
            .toList();
        final caused = agentItems
            .where((r) => r.direction == 'forward' && !_isStructural(r.kind))
            .toList();
        final sameContext =
            agentItems.where((r) => _isStructural(r.kind)).toList();

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(child: Section('Related events')),
                if (onAddLink != null)
                  TextButton.icon(
                    onPressed: onAddLink,
                    icon: const Icon(Icons.add_link, size: 18),
                    label: const Text('Link this event'),
                    style: TextButton.styleFrom(
                      visualDensity: VisualDensity.compact,
                    ),
                  ),
              ],
            ),
            if (loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (items.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text('No connected events linked yet.'),
              )
            else ...[
              _RelatedGroup(
                icon: Icons.south_west,
                title: 'What led to this',
                items: ledTo,
                onSelect: onSelect,
              ),
              _RelatedGroup(
                icon: Icons.north_east,
                title: 'What this caused',
                items: caused,
                onSelect: onSelect,
              ),
              _RelatedGroup(
                icon: Icons.hub_outlined,
                title: 'Same place / same actors',
                items: sameContext,
                onSelect: onSelect,
              ),
              _RelatedGroup(
                icon: Icons.person_add_alt_1_outlined,
                title: 'Added by a user',
                items: userAdded,
                onSelect: onSelect,
              ),
            ],
          ],
        );
      },
    );
  }
}

/// One labelled horizontal strip of related-event cards; renders nothing when empty so
/// only the groups that have links take up space.
class _RelatedGroup extends StatelessWidget {
  const _RelatedGroup({
    required this.icon,
    required this.title,
    required this.items,
    required this.onSelect,
  });

  final IconData icon;
  final String title;
  final List<RelatedEvent> items;
  final void Function(String eventId) onSelect;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 16, color: theme.colorScheme.primary),
              const SizedBox(width: 6),
              Text('$title  (${items.length})',
                  style: theme.textTheme.titleSmall),
            ],
          ),
          const SizedBox(height: 8),
          SizedBox(
            height: 96,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: items.length,
              separatorBuilder: (_, _) => const SizedBox(width: 8),
              itemBuilder: (_, i) => _RelatedCard(
                item: items[i],
                onTap: () => onSelect(items[i].event.id),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _RelatedCard extends StatelessWidget {
  const _RelatedCard({required this.item, required this.onTap});
  final RelatedEvent item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = item.event;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        width: 220,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: theme.colorScheme.outlineVariant),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(item.kind,
                style: theme.textTheme.labelSmall,
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
            const SizedBox(height: 4),
            Expanded(
              child: Text(e.title,
                  style: theme.textTheme.bodySmall,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
            ),
            Text(
              formatLabel(e.tStart, e.precision, instant: e.instant),
              style: theme.textTheme.labelSmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}
