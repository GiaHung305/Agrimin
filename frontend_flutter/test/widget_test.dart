import 'package:flutter_test/flutter_test.dart';

import 'package:frontend_flutter/main.dart';
import 'package:frontend_flutter/models/chat_response.dart';
import 'package:frontend_flutter/widgets/status_badge_icon.dart';
import 'package:flutter/material.dart';

void main() {
  test('resolved chat action is removed from the rendered response state', () {
    final response = ChatResponse(
      answer: 'Đã tạo đề xuất.',
      citations: const [],
      confidence: 1,
      riskLevel: 'low',
      pendingAction: const {
        'id': 'action-1',
        'type': 'create_task',
        'payload': <String, dynamic>{},
      },
    );

    final resolved = response.withoutPendingAction();

    expect(resolved.pendingAction, isNull);
    expect(resolved.answer, response.answer);
  });

  testWidgets('AgriMind AI app renders chat screen', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const AgriMindApp());

    // Xác nhận tiêu đề app hiển thị đúng
    expect(find.text('AgriMind AI'), findsOneWidget);
  });

  testWidgets('notification icon shows a small unread badge', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: StatusBadgeIcon(
            icon: Icons.notifications_none_rounded,
            selectedIcon: Icons.notifications_rounded,
            showBadge: true,
            activeSemanticsLabel: 'Có thông báo mới chưa đọc',
            inactiveSemanticsLabel: 'Không có thông báo mới',
            badgeKey: Key('unread-notification-badge'),
          ),
        ),
      ),
    );

    expect(find.byType(StatusBadgeIcon), findsOneWidget);
    expect(find.byKey(const Key('unread-notification-badge')), findsOneWidget);
    expect(find.bySemanticsLabel('Có thông báo mới chưa đọc'), findsOneWidget);
  });

  testWidgets('task icon shows a badge while work is open', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: StatusBadgeIcon(
            icon: Icons.checklist_outlined,
            selectedIcon: Icons.checklist_rounded,
            showBadge: true,
            activeSemanticsLabel: 'Có công việc đang làm',
            inactiveSemanticsLabel: 'Không có công việc đang làm',
            badgeKey: Key('open-task-badge'),
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('open-task-badge')), findsOneWidget);
    expect(find.bySemanticsLabel('Có công việc đang làm'), findsOneWidget);
  });
}
