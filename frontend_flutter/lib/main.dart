import 'package:flutter/material.dart';
import 'screens/chat_screen.dart';

void main() {
  runApp(const AgriMindApp());
}

class AgriMindApp extends StatelessWidget {
  const AgriMindApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AgriMind AI',
      theme: ThemeData(primarySwatch: Colors.green),
      home: const ChatScreen(),
    );
  }
}