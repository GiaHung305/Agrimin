import 'package:flutter/material.dart';
import '../models/chat_response.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../widgets/message_bubble.dart';
import '../widgets/chat_input.dart';
import 'admin_screen.dart';
import 'login_screen.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final List<Map<String, dynamic>> _messages = [];
  bool _isLoading = false;

  String? conversationId;

  Future<void> _handleSend(String question) async {
    setState(() {
      _messages.add({"question": question, "response": null, "partialText": ""});
      _isLoading = true;
    });

    try {
      Map<String, dynamic>? meta;
      String accumulatedText = "";

      await for (final event in ApiService.sendMessageStream(question, conversationId)) {
        if (event["type"] == "meta") {
          meta = event["payload"];
        } else if (event["type"] == "chunk") {
          accumulatedText += event["payload"];
          setState(() {
            _messages[_messages.length - 1]["partialText"] = accumulatedText;
          });
        } else if (event["type"] == "done") {
          final response = ChatResponse.fromJson({...?meta, "answer": accumulatedText});
          conversationId = response.conversationId ?? conversationId;
          setState(() {
            _messages[_messages.length - 1]["response"] = response;
            _isLoading = false;
          });
        }
      }
    } catch (e) {
      final errorMessage = e.toString();
      if (errorMessage.contains("hết hạn") || errorMessage.contains("401")) {
        await AuthService.logout();
        if (mounted) {
          Navigator.pushReplacement(
            context,
            MaterialPageRoute(builder: (context) => const LoginScreen()),
          );
        }
        return;
      }
      setState(() {
        _messages[_messages.length - 1]["response"] = ChatResponse(
          answer: "Có lỗi xảy ra: $e",
          citations: [],
          confidence: 0.0,
          riskLevel: "low",
        );
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("AgriMind AI"),
        actions: [
          IconButton(
            icon: const Icon(Icons.folder),
            tooltip: "Quản lý tài liệu",
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (context) => const AdminScreen()),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: "Đăng xuất",
            onPressed: () async {
              await AuthService.logout();
              if (context.mounted) {
                Navigator.pushReplacement(
                  context,
                  MaterialPageRoute(builder: (context) => const LoginScreen()),
                );
              }
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final msg = _messages[index];
                final isLast = index == _messages.length - 1;
                return MessageBubble(
                  question: msg["question"],
                  response: msg["response"],
                  isLoading: isLast && _isLoading && msg["response"] == null,
                  partialText: msg["partialText"],
                );
              },
            ),
          ),
          ChatInput(onSend: _handleSend, isLoading: _isLoading),
        ],
      ),
    );
  }
}