import 'package:flutter_test/flutter_test.dart';

import 'package:frontend_flutter/app/agrimind_app.dart';
import 'package:frontend_flutter/data/models/chat_response.dart';
import 'package:frontend_flutter/data/models/registration_result.dart';
import 'package:frontend_flutter/design_system/design_system.dart';
import 'package:frontend_flutter/features/auth/presentation/login_screen.dart';
import 'package:frontend_flutter/features/auth/presentation/register_screen.dart';
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

  testWidgets('AgriMind app renders its initial loading state', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const AgriMindApp());

    expect(find.text('Đang chuẩn bị AgriMind…'), findsOneWidget);
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

  testWidgets('login opens the dedicated registration flow', (tester) async {
    await tester.pumpWidget(
      MaterialApp(theme: buildAppTheme(), home: const LoginScreen()),
    );

    await tester.ensureVisible(find.byKey(const Key('open-register-button')));
    await tester.tap(find.byKey(const Key('open-register-button')));
    await tester.pumpAndSettle();

    expect(find.byType(RegisterScreen), findsOneWidget);
    expect(find.text('Tạo tài khoản mới'), findsOneWidget);
  });

  testWidgets('registration validates fields before calling auth', (
    tester,
  ) async {
    var callCount = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: RegisterScreen(
          onRegister:
              ({
                required email,
                required password,
                required displayName,
              }) async {
                callCount++;
                return const RegistrationResult.authenticated();
              },
        ),
      ),
    );

    await tester.ensureVisible(find.byKey(const Key('register-submit-button')));
    await tester.tap(find.byKey(const Key('register-submit-button')));
    await tester.pump();

    expect(callCount, 0);
    expect(find.text('Vui lòng nhập tên của bạn.'), findsOneWidget);
    expect(find.text('Vui lòng nhập email hợp lệ.'), findsOneWidget);
    expect(find.text('Mật khẩu cần ít nhất 8 ký tự.'), findsOneWidget);
  });

  testWidgets('registration explains email confirmation clearly', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: RegisterScreen(
          onRegister:
              ({
                required email,
                required password,
                required displayName,
              }) async => const RegistrationResult.confirmationRequired(),
        ),
      ),
    );

    await tester.enterText(
      find.byKey(const Key('register-name-field')),
      'Nguyễn Văn An',
    );
    await tester.enterText(
      find.byKey(const Key('register-email-field')),
      'an@example.com',
    );
    await tester.enterText(
      find.byKey(const Key('register-password-field')),
      'Matkhau@123',
    );
    await tester.enterText(
      find.byKey(const Key('register-confirm-field')),
      'Matkhau@123',
    );
    await tester.ensureVisible(find.byKey(const Key('register-submit-button')));
    await tester.tap(find.byKey(const Key('register-submit-button')));
    await tester.pumpAndSettle();

    expect(find.text('Kiểm tra email của bạn'), findsOneWidget);
    expect(find.textContaining('an@example.com'), findsOneWidget);
    expect(find.text('Quay lại đăng nhập'), findsOneWidget);
  });
}
