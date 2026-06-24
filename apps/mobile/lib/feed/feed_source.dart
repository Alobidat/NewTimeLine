/// The feed data contract for the TikTok-style client (ADR-0027, social-and-feed §4/§5).
///
/// The product feed is **video-first**: each tab (For You / Following / Discover) returns a
/// ranked list of clip-bearing events from the live recommendation API (social-and-feed §4):
///
///   GET /feed/{foryou|following|discover}?cursor=…&limit=…
///     → {tab, items:[{event, hero_media_id, score}], next_cursor}
///
/// A [FeedItem] is an [EventRead] plus the already-known hero clip id; pages are cursor-
/// paginated via the opaque `next_cursor` (null when the feed is exhausted). [FeedSource]
/// owns only the mapping from the wire shape to [FeedItem] — the rest of the UI consumes
/// [FeedItem]/[FeedPage] unchanged.
library;

import '../api/client.dart';
import '../api/models.dart';

/// The three feed tabs (social-and-feed §5).
enum FeedTab {
  forYou('For You', 'foryou'),
  following('Following', 'following'),
  discover('Discover', 'discover');

  const FeedTab(this.label, this.slug);

  /// The human tab label.
  final String label;

  /// The path segment for the `/feed/{slug}` endpoint.
  final String slug;
}

/// One video-first card in the feed: an event and (optionally) the id of its hero clip.
/// The hero clip is the muted, looping autoplay video shown full-screen. When [heroMediaId]
/// is null the item still renders (poster / placeholder) — the feed never drops a card.
class FeedItem {
  const FeedItem({
    required this.event,
    this.heroMediaId,
    this.heroIsClip = false,
    this.author,
    this.authorKind = 'user',
  });

  final EventRead event;
  final String? heroMediaId;

  /// Whether [heroMediaId] is a playable clip (video/embed) vs a still image. Image heroes are
  /// rendered as a full-bleed photo — feeding a JPEG to a `<video>` is what showed a black
  /// screen. Defaults false (no hero → placeholder).
  final bool heroIsClip;

  /// Who to attribute the clip to (rail avatar + follow): the uploading *user* for
  /// user-generated clips, else the clip's primary *entity* (e.g. NASA) for agent-curated
  /// events. Null only when nothing is known.
  final CommentAuthor? author;

  /// Whether [author] is a `user` (follow + open their profile) or an `entity` (follow the
  /// entity; no personal profile). Drives the follow target + tap behaviour.
  final String authorKind;

  String get id => event.id;

  factory FeedItem.fromJson(Map<String, dynamic> j) => FeedItem(
    event: EventRead.fromJson(j['event'] as Map<String, dynamic>),
    heroMediaId: j['hero_media_id'] as String?,
    // Absent field ⇒ an older backend that predates the flag: assume clip, preserving the
    // established video-first rendering (defaulting to image would break working video cards
    // during a frontend-before-backend deploy). New backends always send the real value.
    heroIsClip: j['hero_is_clip'] as bool? ?? true,
    author: j['author'] is Map<String, dynamic>
        ? CommentAuthor.fromJson(j['author'] as Map<String, dynamic>)
        : null,
    authorKind: j['author_kind'] as String? ?? 'user',
  );
}

/// A page of feed items plus an opaque cursor for the next page (null when exhausted).
class FeedPage {
  const FeedPage({required this.items, this.nextCursor});
  final List<FeedItem> items;
  final String? nextCursor;
}

/// Fetches pages of [FeedItem]s for a tab from the live `/feed/{slug}` ranking endpoint.
class FeedSource {
  FeedSource(this.api);
  final ApiClient api;

  /// Fetch one page for [tab]. [cursor] is the opaque token from the previous [FeedPage]
  /// (null for the first page). [limit] caps the page size. Maps the live
  /// `{items:[{event, hero_media_id, score}], next_cursor}` response to [FeedItem]s.
  Future<FeedPage> page(FeedTab tab, {String? cursor, int limit = 20}) async {
    final json = await api.feedPage(tab.slug, cursor: cursor, limit: limit);
    final rawItems = (json['items'] as List?) ?? const [];
    return FeedPage(
      items: [
        for (final it in rawItems)
          FeedItem.fromJson(it as Map<String, dynamic>),
      ],
      nextCursor: json['next_cursor'] as String?,
    );
  }
}

/// A [FeedSource] decorator whose **first page is prefixed with a seed event**, so an
/// immersive feed can open focused on one specific event (a graph-node tap, a related-event
/// pivot, or a shared deep link) and still keep paging the underlying ranked feed afterwards.
class SeededFeedSource extends FeedSource {
  SeededFeedSource(this._inner, this._seed) : super(_inner.api);
  final FeedSource _inner;
  final EventRead _seed;
  bool _seeded = false;

  @override
  Future<FeedPage> page(FeedTab tab, {String? cursor, int limit = 20}) async {
    final base = await _inner.page(tab, cursor: cursor, limit: limit);
    if (_seeded) return base;
    _seeded = true;
    return FeedPage(
      items: [
        FeedItem(event: _seed),
        ...base.items.where((i) => i.id != _seed.id),
      ],
      nextCursor: base.nextCursor,
    );
  }
}
