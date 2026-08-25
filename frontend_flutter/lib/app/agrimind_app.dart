import 'package:flutter/material.dart';

import 'package:frontend_flutter/design_system/design_system.dart';

import 'app_gate.dart';

class AgriMindApp extends StatelessWidget {
  const AgriMindApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AgriMind AI',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      darkTheme: buildAppDarkTheme(),
      themeMode: ThemeMode.system,
      home: const AppGate(),
    );
  }
}
