/// Off-web stub for [prefetchClips]: native `video_player` does its own buffering for the
/// preload neighbours, so there is nothing to warm here. See [prefetch_web.dart] for the web
/// `<link rel="prefetch">` warming.
library;

void prefetchClips(List<String> urls) {}
