import 'package:flutter/material.dart';

import '../models/chat_response.dart';
import '../models/chat_image.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../services/push_notification_service.dart';
import '../theme/app_theme.dart';
import '../widgets/chat_input.dart';
import '../widgets/message_bubble.dart';
import 'admin_screen.dart';
import 'farm_profile_screen.dart';
import 'login_screen.dart';
import 'notifications_screen.dart';
import 'tasks_screen.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final List<Map<String, dynamic>> _messages = [];
  final ScrollController _scrollController = ScrollController();
  bool _isLoading = false;
  String? conversationId;

  @override
  void initState() {
    super.initState();
    PushNotificationService.registerCurrentDevice().catchError((_) {});
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToLatest() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 240),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _resolveAction(String actionId, bool confirmed) async {
    try {
      await ApiService.resolveAssistantAction(actionId, confirmed);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              confirmed ? 'Đã tạo công việc theo đề xuất' : 'Đã hủy đề xuất',
            ),
          ),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Có lỗi: $error')));
      }
    }
  }

  Future<void> _handleSend(
    String question,
    bool deepResearch,
    List<ChatImageAttachment> images,
  ) async {
    setState(() {
      _messages.add({
        'question': question,
        'response': null,
        'partialText': '',
        'imageCount': images.length,
      });
      _isLoading = true;
    });
    _scrollToLatest();
    try {
      Map<String, dynamic>? meta;
      var accumulatedText = '';
      await for (final event in ApiService.sendMessageStream(
        question,
        conversationId,
        deepResearch,
        images,
      )) {
        if (event['type'] == 'meta') {
          meta = event['payload'];
        } else if (event['type'] == 'chunk') {
          accumulatedText += event['payload'];
          if (mounted) {
            setState(() => _messages.last['partialText'] = accumulatedText);
            _scrollToLatest();
          }
        } else if (event['type'] == 'done') {
          final response = ChatResponse.fromJson({
            ...?meta,
            'answer': accumulatedText,
          });
          conversationId = response.conversationId ?? conversationId;
          if (mounted) {
            setState(() {
              _messages.last['response'] = response;
              _isLoading = false;
            });
            _scrollToLatest();
          }
        }
      }
    } catch (error) {
      final message = error.toString();
      if (message.contains('401')) {
        await AuthService.logout();
        if (mounted) {
          Navigator.pushReplacement(
            context,
            MaterialPageRoute(builder: (_) => const LoginScreen()),
          );
        }
        return;
      }
      if (mounted) {
        setState(() {
          final isImageError =
              message.contains('Ảnh') || message.contains('ảnh');
          _messages.last['response'] = ChatResponse(
            answer: isImageError
                ? message.replaceFirst('Exception: ', '')
                : 'Mình chưa thể kết nối lúc này. Bạn thử lại sau ít phút nhé.',
            citations: const [],
            confidence: 0,
            riskLevel: 'low',
          );
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _onMenu(String value) async {
    if (value == 'tasks') {
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const TasksScreen()),
      );
    } else if (value == 'farm') {
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const FarmProfileScreen()),
      );
    } else if (value == 'documents') {
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const AdminScreen()),
      );
    } else if (value == 'logout') {
      await AuthService.logout();
      if (mounted) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const LoginScreen()),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 76,
        title: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(
                color: AppColors.forest,
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.spa_rounded,
                color: Colors.white,
                size: 25,
              ),
            ),
            const SizedBox(width: 11),
            const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'AgriMind',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 19),
                ),
                Row(
                  children: [
                    Icon(Icons.circle, color: Color(0xFF48AF67), size: 9),
                    SizedBox(width: 5),
                    Text(
                      'Trợ lý nông nghiệp',
                      style: TextStyle(fontSize: 12, color: AppColors.muted),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Thông báo',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const NotificationsScreen()),
            ),
            icon: const Icon(Icons.notifications_none_rounded),
          ),
          Container(
            margin: const EdgeInsets.only(right: 8),
            decoration: const BoxDecoration(
              color: Colors.white,
              shape: BoxShape.circle,
            ),
            child: PopupMenuButton<String>(
              tooltip: 'Menu',
              icon: const Icon(Icons.more_horiz_rounded),
              onSelected: _onMenu,
              itemBuilder: (context) => const [
                PopupMenuItem(
                  value: 'farm',
                  child: ListTile(
                    leading: Icon(Icons.agriculture_outlined),
                    title: Text('Nông trại của tôi'),
                  ),
                ),
                PopupMenuItem(
                  value: 'tasks',
                  child: ListTile(
                    leading: Icon(Icons.checklist_rounded),
                    title: Text('Công việc'),
                  ),
                ),
                PopupMenuItem(
                  value: 'documents',
                  child: ListTile(
                    leading: Icon(Icons.folder_outlined),
                    title: Text('Tài liệu'),
                  ),
                ),
                PopupMenuDivider(),
                PopupMenuItem(
                  value: 'logout',
                  child: ListTile(
                    leading: Icon(Icons.logout_rounded),
                    title: Text('Đăng xuất'),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: _messages.isEmpty
                ? _WelcomePanel(
                    onPrompt: (prompt) => _handleSend(prompt, false, const []),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 18),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      final message = _messages[index];
                      return MessageBubble(
                        question: message['question'],
                        imageCount: message['imageCount'] ?? 0,
                        response: message['response'],
                        isLoading:
                            index == _messages.length - 1 &&
                            _isLoading &&
                            message['response'] == null,
                        partialText: message['partialText'],
                        onResolveAction: _resolveAction,
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

class _WelcomePanel extends StatelessWidget {
  final ValueChanged<String> onPrompt;

  const _WelcomePanel({required this.onPrompt});

  @override
  Widget build(BuildContext context) {
    const prompts = [
      ('☀️', 'Thời tiết hôm nay', 'Xem dự báo cho nông trại của tôi'),
      ('🌱', 'Tư vấn cây trồng', 'Cây đang vàng lá thì nên kiểm tra gì?'),
      ('⏰', 'Tạo nhắc việc', 'Nhắc tôi kiểm tra ruộng ngày mai lúc 7 giờ'),
    ];
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 22, 20, 30),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(22),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [AppColors.forest, AppColors.forestDark],
              ),
              borderRadius: BorderRadius.circular(26),
            ),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Chào bạn 👋',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                SizedBox(height: 8),
                Text(
                  'Mình sẵn sàng hỗ trợ chăm sóc nông trại, theo dõi thời tiết và nhắc việc đúng lúc.',
                  style: TextStyle(color: Color(0xFFD9F3E4), height: 1.4),
                ),
              ],
            ),
          ),
          const SizedBox(height: 26),
          const Text(
            'Bạn muốn làm gì?',
            style: TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w800,
              color: AppColors.ink,
            ),
          ),
          const SizedBox(height: 12),
          ...prompts.map(
            (prompt) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Card(
                child: InkWell(
                  onTap: () => onPrompt(prompt.$3),
                  borderRadius: BorderRadius.circular(22),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        Text(prompt.$1, style: const TextStyle(fontSize: 24)),
                        const SizedBox(width: 13),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                prompt.$2,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.ink,
                                ),
                              ),
                              const SizedBox(height: 3),
                              Text(
                                prompt.$3,
                                style: const TextStyle(
                                  fontSize: 12,
                                  color: AppColors.muted,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const Icon(
                          Icons.arrow_forward_ios_rounded,
                          size: 15,
                          color: AppColors.forest,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
