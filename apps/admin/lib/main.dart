/// Chronos (NewTimeLine) Admin Portal entrypoint.
library;

import 'package:flutter/material.dart';

import 'shell/admin_shell.dart';

void main() => runApp(const ChronosAdminApp());

class ChronosAdminApp extends StatelessWidget {
  const ChronosAdminApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Chronos Admin',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorSchemeSeed: const Color(0xFF2E7DF6),
      ),
      home: const AdminShell(),
    );
  }
}
