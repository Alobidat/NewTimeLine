/// Chronos (NewTimeLine) client entrypoint — opens on the TikTok-style video feed
/// (ADR-0027). The classic map/timeline experience stays reachable from the feed's overflow
/// menu and the graph/timeline-web view.
library;

import 'package:flutter/material.dart';

import 'feed/feed_home.dart';

void main() => runApp(const ChronosApp());

class ChronosApp extends StatelessWidget {
  const ChronosApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Chronos',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorSchemeSeed: const Color(0xFF2E7DF6),
      ),
      home: const FeedHome(),
    );
  }
}
