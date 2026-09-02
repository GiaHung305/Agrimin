import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:frontend_flutter/app/agrimind_app.dart';
import 'package:frontend_flutter/data/models/chat_response.dart';
import 'package:frontend_flutter/data/models/registration_result.dart';
import 'package:frontend_flutter/data/services/api_service.dart';
import 'package:frontend_flutter/design_system/design_system.dart';
import 'package:frontend_flutter/features/auth/presentation/login_screen.dart';
import 'package:frontend_flutter/features/auth/presentation/register_screen.dart';
import 'package:frontend_flutter/features/auth/presentation/forgot_password_screen.dart';
import 'package:frontend_flutter/features/assistant/presentation/chat_screen.dart';
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

  testWidgets('truncated chat stream releases the composer for another send', (
    tester,
  ) async {
    var calls = 0;
    final receivedConversationIds = <String?>[];
    Stream<Map<String, dynamic>> send(_, String? sentConversationId, _, _) {
      calls++;
      receivedConversationIds.add(sentConversationId);
      if (calls == 1) {
        return Stream.fromIterable(const [
          {
            'type': 'meta',
            'payload': {'conversation_id': 'conversation-1'},
          },
        ]);
      }
      return Stream.fromIterable(const [
        {
          'type': 'meta',
          'payload': {
            'conversation_id': 'conversation-1',
            'confidence': 0.8,
            'risk_level': 'low',
            'guardrail_status': 'pass',
          },
        },
        {'type': 'chunk', 'payload': 'Đã kết nối lại.'},
        {'type': 'done'},
      ]);
    }

    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: ChatScreen(sendMessageStream: send),
      ),
    );

    await tester.enterText(find.byType(TextField), 'Kiểm tra kết nối');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(
      find.text(
        'Phản hồi bị gián đoạn trước khi hoàn tất. Bạn có thể thử lại ngay.',
      ),
      findsOneWidget,
    );
    expect(find.byIcon(Icons.arrow_upward_rounded), findsOneWidget);
    expect(find.byKey(const Key('retry-chat-message')), findsOneWidget);

    await tester.tap(find.byKey(const Key('retry-chat-message')));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(receivedConversationIds, [null, 'conversation-1']);
    expect(find.text('Đã kết nối lại.'), findsOneWidget);
    expect(find.byKey(const Key('chat-error-card')), findsNothing);
  });

  testWidgets('temporary service response retries in place', (tester) async {
    var calls = 0;
    Stream<Map<String, dynamic>> send(_, _, _, _) {
      calls++;
      if (calls == 1) {
        return Stream.fromIterable(const [
          {'type': 'chunk', 'payload': 'Dịch vụ đang tạm bận.'},
          {
            'type': 'meta',
            'payload': {
              'confidence': 0,
              'risk_level': 'low',
              'guardrail_status': 'block',
              'trace': {
                'guardrail': {'response_kind': 'service_status'},
              },
            },
          },
          {'type': 'done'},
        ]);
      }
      return Stream.fromIterable(const [
        {'type': 'chunk', 'payload': 'Đã kết nối lại.'},
        {
          'type': 'meta',
          'payload': {
            'confidence': 0.8,
            'risk_level': 'low',
            'guardrail_status': 'pass',
          },
        },
        {'type': 'done'},
      ]);
    }

    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: ChatScreen(sendMessageStream: send),
      ),
    );

    await tester.enterText(find.byType(TextField), 'Cách tưới cà chua?');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(find.text('Dịch vụ đang tạm bận.'), findsOneWidget);
    expect(find.byKey(const Key('retry-chat-response')), findsOneWidget);

    await tester.tap(find.byKey(const Key('retry-chat-response')));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.text('Cách tưới cà chua?'), findsOneWidget);
    expect(find.text('Đã kết nối lại.'), findsOneWidget);
    expect(find.text('Dịch vụ đang tạm bận.'), findsNothing);
  });

  testWidgets('chat shows friendly progress stages while waiting', (
    tester,
  ) async {
    final controller = StreamController<Map<String, dynamic>>();
    Stream<Map<String, dynamic>> send(_, _, _, _) => controller.stream;

    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: ChatScreen(sendMessageStream: send),
      ),
    );
    await tester.enterText(find.byType(TextField), 'Cách chăm cà chua?');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();

    expect(find.text('Đang hiểu câu hỏi…'), findsOneWidget);

    controller.add(const {
      'type': 'progress',
      'payload': 'Đang đối chiếu nguồn đáng tin cậy…',
    });
    await tester.pump();

    expect(find.text('Đang đối chiếu nguồn đáng tin cậy…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.tap(find.byKey(const Key('cancel-chat-response')));
    await tester.pumpAndSettle();
  });

  testWidgets('user can cancel an unfinished stream and retry in place', (
    tester,
  ) async {
    var cancelled = false;
    late final StreamController<Map<String, dynamic>> controller;
    controller = StreamController<Map<String, dynamic>>(
      onCancel: () {
        cancelled = true;
      },
    );

    Stream<Map<String, dynamic>> send(_, _, _, _) => controller.stream;

    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: ChatScreen(sendMessageStream: send),
      ),
    );
    await tester.enterText(find.byType(TextField), 'Cách chăm cà chua?');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();
    controller.add(const {'type': 'chunk', 'payload': 'Nội dung chưa xong'});
    await tester.pump();

    expect(find.byKey(const Key('cancel-chat-response')), findsOneWidget);
    expect(find.text('Nội dung chưa xong'), findsOneWidget);

    await tester.tap(find.byKey(const Key('cancel-chat-response')));
    await tester.pumpAndSettle();

    expect(cancelled, isTrue);
    expect(find.text('Nội dung chưa xong'), findsNothing);
    expect(
      find.text('Bạn đã dừng câu trả lời. Bạn có thể thử lại khi sẵn sàng.'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('retry-chat-message')), findsOneWidget);
    expect(find.byKey(const Key('send-chat-message')), findsOneWidget);
  });

  test('chat errors map status codes to friendly recovery guidance', () {
    expect(
      friendlyChatError(const ApiException('quota', statusCode: 429)),
      contains('chờ một chút'),
    );
    expect(
      friendlyChatError(const ApiException('unavailable', statusCode: 503)),
      contains('tạm bận'),
    );
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

  testWidgets('login opens password recovery', (tester) async {
    await tester.pumpWidget(
      MaterialApp(theme: buildAppTheme(), home: const LoginScreen()),
    );

    await tester.tap(find.byKey(const Key('forgot-password-button')));
    await tester.pumpAndSettle();

    expect(find.byType(ForgotPasswordScreen), findsOneWidget);
    expect(find.text('Lấy lại mật khẩu'), findsOneWidget);
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

  testWidgets('regular users do not see document administration', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(theme: buildAppTheme(), home: const ChatScreen()),
    );

    await tester.tap(find.byTooltip('Menu'));
    await tester.pumpAndSettle();

    expect(find.text('Tài liệu'), findsNothing);
  });

  testWidgets('admins see document administration in the menu', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: const ChatScreen(canManageDocuments: true),
      ),
    );

    await tester.tap(find.byTooltip('Menu'));
    await tester.pumpAndSettle();

    expect(find.text('Tài liệu'), findsOneWidget);
  });

  testWidgets('regular users do not see operations dashboard', (tester) async {
    await tester.pumpWidget(
      MaterialApp(theme: buildAppTheme(), home: const ChatScreen()),
    );

    await tester.tap(find.byTooltip('Menu'));
    await tester.pumpAndSettle();

    expect(find.text('Vận hành hệ thống'), findsNothing);
  });

  testWidgets('operations admins see the worker dashboard entry', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: const ChatScreen(canViewOperations: true),
      ),
    );

    await tester.tap(find.byTooltip('Menu'));
    await tester.pumpAndSettle();

    expect(find.text('Vận hành hệ thống'), findsOneWidget);
  });
}
