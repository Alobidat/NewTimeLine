/// The feed data contract for the TikTok-style client (ADR-0027, social-and-feed §4/§5).
///
/// The product feed is **video-first**: each tab (For You / Following / Discover) returns a
/// ranked list of clip-bearing events. The real ranking endpoints
/// (`/feed/foryou|following|discover`, social-and-feed §4) are built by the backend in a
/// parallel wave and are **NOT live yet** — so this source is a thin shim over the existing
/// public endpoints (`/timeline`, `/search`) that returns the same shape the UI needs.
///
/// A [FeedItem] is an [EventRead] plus an optional already-known hero clip. When the real
/// `/feed` lands the events arrive pre-ranked and already carry a hero media id, so the only
/// change here is the fetch call — the rest of the UI consumes [FeedItem] unchanged.
///
/// TODO(phase-4-B / IU2): swap [FeedSource.page] to call
///   GET /feed/{foryou|following|discover}?cursor=…&limit=…
/// which returns `{items:[{event, hero_media_id, score}], next_cursor}`. Keep [FeedItem] and
/// [FeedTab] as-is; delete the `_fallback*` methods below.
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

  /// The path segment for the (future) `/feed/{slug}` endpoint.
  final String slug;
}

/// One video-first card in the feed: an event and (optionally) the id of its hero clip.
/// The hero clip is the muted, looping autoplay video shown full-screen. When [heroMediaId]
/// is null the item still renders (poster / placeholder) — the feed never drops a card.
class FeedItem {
  const FeedItem({required this.event, this.heroMediaId});

  final EventRead event;
  final String? heroMediaId;

  String get id => event.id;

  factory FeedItem.fromJson(Map<String, dynamic> j) => FeedItem(
    event: EventRead.fromJson(j['event'] as Map<String, dynamic>),
    heroMediaId: j['hero_media_id'] as String?,
  );
}

/// A page of feed items plus an opaque cursor for the next page (null when exhausted).
class FeedPage {
  const FeedPage({required this.items, this.nextCursor});
  final List<FeedItem> items;
  final String? nextCursor;
}

/// Fetches pages of [FeedItem]s for a tab. Backed today by existing endpoints; swap to
/// `/feed/{slug}` when the rec API lands (see file header TODO).
class FeedSource {
  FeedSource(this.api);
  final ApiClient api;

  /// Fetch one page for [tab]. [cursor] is the opaque token from the previous [FeedPage]
  /// (null for the first page). [limit] caps the page size.
  Future<FeedPage> page(FeedTab tab, {String? cursor, int limit = 20}) async {
    // TODO(phase-4-B): replace this whole body with a single GET /feed/{tab.slug}.
    // Until then, derive a video-first list from the public endpoints so the shell is
    // fully exercisable against a live backend without the rec API.
    final events = await _fallbackEvents(limit: limit);
    // The shim has no real pagination, so it returns a single page (nextCursor == null).
    // The real endpoint will thread `next_cursor` through unchanged.
    return FeedPage(
      items: [for (final e in events) FeedItem(event: e)],
      nextCursor: null,
    );
  }

  /// TODO(phase-4-B): delete. Pulls a broad, recent-leaning event window from /timeline as a
  /// stand-in for a ranked feed. Falls back to a wide search if the window is empty.
  Future<List<EventRead>> _fallbackEvents({required int limit}) async {
    try {
      final resp = await api.timeline(
        t0: -5000,
        t1: 3000,
        maxEvents: limit,
        buckets: limit,
      );
      if (resp.events.isNotEmpty) return resp.events.take(limit).toList();
    } catch (_) {
      // fall through to search
    }
    try {
      final res = await api.search(q: 'history', limit: limit, collect: false);
      return res.events.take(limit).toList();
    } catch (_) {
      return const [];
    }
  }
}
