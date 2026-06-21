/// The app home (ADR-0027): a full-bleed, immersive scaffold with the three feed tabs
/// **For You / Following / Discover** over a vertical video feed each. The tab bar floats at
/// the top over the video (TikTok-style); a menu affords the classic map/timeline
/// [ExperienceScreen] so the prior experience is never lost.
///
/// Each tab owns its own [VideoFeed] (kept alive across tab switches). All three share one
/// [FeedSource] + [ApiClient] (closed when the home is torn down).
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../shell/experience_screen.dart';
import 'feed_source.dart';
import 'video_feed.dart';

class FeedHome extends StatefulWidget {
  const FeedHome({super.key, this.api});

  /// Injectable for tests; defaults to a real [ApiClient].
  final ApiClient? api;

  @override
  State<FeedHome> createState() => _FeedHomeState();
}

class _FeedHomeState extends State<FeedHome>
    with SingleTickerProviderStateMixin {
  late final ApiClient _api = widget.api ?? ApiClient();
  late final bool _ownsApi = widget.api == null;
  late final FeedSource _source = FeedSource(_api);
  late final TabController _tabs =
      TabController(length: FeedTab.values.length, vsync: this);

  @override
  void dispose() {
    _tabs.dispose();
    if (_ownsApi) _api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      extendBodyBehindAppBar: true,
      body: Stack(
        children: [
          // The feeds fill the screen behind the floating tab bar.
          Positioned.fill(
            child: TabBarView(
              controller: _tabs,
              children: [
                for (final tab in FeedTab.values)
                  VideoFeed(
                    key: ValueKey('videofeed-${tab.slug}'),
                    api: _api,
                    source: _source,
                    tab: tab,
                  ),
              ],
            ),
          ),
          // Floating top bar: the three tabs + an overflow menu to the classic experience.
          SafeArea(
            child: Row(
              children: [
                Expanded(
                  child: TabBar(
                    controller: _tabs,
                    isScrollable: true,
                    tabAlignment: TabAlignment.center,
                    indicatorColor: Colors.white,
                    labelColor: Colors.white,
                    unselectedLabelColor: Colors.white60,
                    dividerColor: Colors.transparent,
                    tabs: [
                      for (final tab in FeedTab.values) Tab(text: tab.label),
                    ],
                  ),
                ),
                PopupMenuButton<String>(
                  icon: const Icon(Icons.more_vert, color: Colors.white),
                  onSelected: (v) {
                    if (v == 'experience') {
                      Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => const ExperienceScreen(),
                        ),
                      );
                    }
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(
                      value: 'experience',
                      child: ListTile(
                        leading: Icon(Icons.map_outlined),
                        title: Text('Map & timeline'),
                        contentPadding: EdgeInsets.zero,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
