/// Web implementation of [prefetchClips]: warm the upcoming clip urls with `<link
/// rel="prefetch">` so the browser pulls them into HTTP cache at low priority. When the feed
/// later swaps its visible `<video>` src to one of these urls (see [webVideoView]) it starts
/// from cache → near-instant, satisfying FR-1.3's "pre-buffer the next 2".
///
/// Bounded: we keep only the currently-upcoming set and drop the `<link>`s for clips that have
/// scrolled past, so the document head never accumulates stale prefetch hints.
library;

import 'package:web/web.dart' as web;

final Map<String, web.HTMLLinkElement> _links = {};

void prefetchClips(List<String> urls) {
  final keep = urls.toSet();
  // Drop warmers no longer upcoming.
  _links.removeWhere((url, link) {
    if (keep.contains(url)) return false;
    link.remove();
    return true;
  });
  // Add warmers for any new upcoming clip.
  for (final url in urls) {
    if (_links.containsKey(url)) continue;
    final link = web.HTMLLinkElement()
      ..rel = 'prefetch'
      ..href = url;
    link.setAttribute('as', 'video'); // resource-type hint for the prefetch
    web.document.head?.appendChild(link);
    _links[url] = link;
  }
}
