/// Chronos (NewTimeLine) client entrypoint — opens on the magical timeline.
library;

import 'package:flutter/material.dart';

import 'shell/experience_screen.dart';

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
      home: const ExperienceScreen(),
    );
  }
}
