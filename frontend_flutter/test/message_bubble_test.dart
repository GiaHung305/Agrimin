import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend_flutter/data/models/chat_response.dart';
import 'package:frontend_flutter/features/assistant/presentation/widgets/message_bubble.dart';

void main() {
  testWidgets('assistant answer renders Markdown instead of raw markers', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Cây đang ở giai đoạn nào?',
            response: ChatResponse(
              answer: '**Giai đoạn:** cây con\n\n- Theo dõi độ ẩm',
              citations: const [],
              confidence: 0.9,
              riskLevel: 'low',
              guardrailStatus: 'pass',
            ),
          ),
        ),
      ),
    );

    final renderedText = tester
        .widgetList<RichText>(find.byType(RichText))
        .map((widget) => widget.text.toPlainText())
        .join('\n');
    expect(renderedText, contains('Giai đoạn:'));
    expect(renderedText, isNot(contains('**')));
    expect(renderedText, contains('Theo dõi độ ẩm'));
  });

  testWidgets('sources stay compact and technical confidence is hidden', (
    tester,
  ) async {
    Uri? openedUri;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Dứa bị thối nõn cần làm gì?',
            response: ChatResponse(
              answer: 'Ưu tiên kiểm tra thoát nước [E1].',
              citations: const [
                ResearchCitation(
                  citationId: 'E1',
                  title: 'Quy trình phòng chống bệnh trên dứa',
                  url: 'https://example.gov.vn/dua',
                  type: 'internal',
                ),
              ],
              confidence: 0.93,
              riskLevel: 'medium',
              guardrailStatus: 'pass',
              trace: TraceInfo(
                planner: const {'risk_level': 'medium'},
                retriever: const {'docs_found': 1},
                weather: const {},
                reflection: const {},
                guardrail: const {'status': 'pass'},
                research: const {},
                vision: const {},
              ),
            ),
            launchSourceUrl: (uri) async {
              openedUri = uri;
              return true;
            },
          ),
        ),
      ),
    );

    expect(find.text('Nguồn đã dùng (1)'), findsOneWidget);
    expect(find.text('Đã đối chiếu với 1 nguồn'), findsOneWidget);
    expect(find.textContaining('Độ tin cậy'), findsNothing);
    expect(find.text('Cách AgriMind phân tích'), findsNothing);
    expect(find.text('Quy trình phòng chống bệnh trên dứa'), findsNothing);

    await tester.tap(find.text('Nguồn đã dùng (1)'));
    await tester.pumpAndSettle();

    expect(find.text('Quy trình phòng chống bệnh trên dứa'), findsOneWidget);
    expect(find.byTooltip('Mở nguồn'), findsOneWidget);
    expect(find.byTooltip('Sao chép liên kết nguồn'), findsOneWidget);

    await tester.tap(find.byTooltip('Mở nguồn'));
    await tester.pump();
    expect(openedUri, Uri.parse('https://example.gov.vn/dua'));
  });

  testWidgets('unsafe source scheme never exposes link actions', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Hỏi',
            response: ChatResponse(
              answer: 'Khuyến nghị [E1].',
              citations: const [
                ResearchCitation(
                  citationId: 'E1',
                  title: 'Nguồn không hợp lệ',
                  url: 'javascript:alert(1)',
                  type: 'web',
                ),
              ],
              confidence: 0.9,
              riskLevel: 'medium',
              guardrailStatus: 'pass',
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Nguồn đã dùng (1)'));
    await tester.pumpAndSettle();

    expect(find.text('Nguồn không hợp lệ'), findsOneWidget);
    expect(find.byTooltip('Mở nguồn'), findsNothing);
    expect(find.byTooltip('Sao chép liên kết nguồn'), findsNothing);
  });

  testWidgets('source launch failure offers copy fallback', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Hỏi',
            response: ChatResponse(
              answer: 'Khuyến nghị [E1].',
              citations: const [
                ResearchCitation(
                  citationId: 'E1',
                  title: 'Nguồn hợp lệ',
                  url: 'https://example.gov.vn/source',
                  type: 'web',
                ),
              ],
              confidence: 0.9,
              riskLevel: 'medium',
              guardrailStatus: 'pass',
            ),
            launchSourceUrl: (_) async => false,
          ),
        ),
      ),
    );

    await tester.tap(find.text('Nguồn đã dùng (1)'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Mở nguồn'));
    await tester.pump();

    expect(find.textContaining('Không thể mở liên kết nguồn'), findsOneWidget);
    expect(find.byTooltip('Sao chép liên kết nguồn'), findsOneWidget);
  });

  testWidgets('missing cited source is not presented as verified', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Hỏi',
            response: ChatResponse(
              answer: 'Khuyến nghị [E2].',
              citations: const [
                ResearchCitation(
                  citationId: 'E1',
                  title: 'Nguồn khác',
                  type: 'internal',
                ),
              ],
              confidence: 0.9,
              riskLevel: 'medium',
              guardrailStatus: 'pass',
            ),
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('chat-sources-section')), findsNothing);
    expect(
      find.text('Chưa đủ thông tin đáng tin cậy để áp dụng'),
      findsOneWidget,
    );
  });

  testWidgets('unmarked source is reference only and never verified', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Hỏi',
            response: ChatResponse(
              answer: 'Khuyến nghị chung chưa gắn nguồn.',
              citations: const [
                ResearchCitation(
                  citationId: 'E1',
                  title: 'Tài liệu kỹ thuật',
                  type: 'internal',
                ),
              ],
              confidence: 0.9,
              riskLevel: 'medium',
              guardrailStatus: 'pass',
            ),
          ),
        ),
      ),
    );

    expect(find.text('Nguồn tham khảo (1)'), findsOneWidget);
    expect(find.text('Đã đối chiếu với 1 nguồn'), findsNothing);
    expect(
      find.text('Chưa đủ thông tin đáng tin cậy để áp dụng'),
      findsOneWidget,
    );
  });

  testWidgets('duplicate citation metadata is deduplicated and fails closed', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Hỏi',
            response: ChatResponse(
              answer: 'Khuyến nghị có nguồn [E1].',
              citations: const [
                ResearchCitation(
                  citationId: 'E1',
                  title: 'Tài liệu kỹ thuật',
                  type: 'internal',
                ),
                ResearchCitation(
                  citationId: 'E1',
                  title: 'Bản ghi trùng',
                  type: 'internal',
                ),
              ],
              confidence: 0.9,
              riskLevel: 'medium',
              guardrailStatus: 'pass',
            ),
          ),
        ),
      ),
    );

    expect(find.text('Nguồn đã dùng (1)'), findsOneWidget);
    expect(find.text('Đã đối chiếu với 1 nguồn'), findsNothing);
    expect(
      find.text('Chưa đủ thông tin đáng tin cậy để áp dụng'),
      findsOneWidget,
    );
  });

  testWidgets('low confidence pass is not presented as verified', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Hỏi',
            response: ChatResponse(
              answer: 'Thông tin hiện còn hạn chế.',
              citations: const [],
              confidence: 0.42,
              riskLevel: 'low',
              guardrailStatus: 'pass',
            ),
          ),
        ),
      ),
    );

    expect(find.text('Đã kiểm tra trước khi phản hồi'), findsNothing);
    expect(
      find.text('Chưa đủ thông tin đáng tin cậy để áp dụng'),
      findsOneWidget,
    );
  });

  testWidgets('high confidence without sources avoids a generic trust badge', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Cây đang ở giai đoạn nào?',
            response: ChatResponse(
              answer: 'Cây đang ở giai đoạn cây con.',
              citations: const [],
              confidence: 0.9,
              riskLevel: 'low',
              guardrailStatus: 'pass',
            ),
          ),
        ),
      ),
    );

    expect(find.textContaining('Đã đối chiếu'), findsNothing);
    expect(find.text('Đã kiểm tra trước khi phản hồi'), findsNothing);
    expect(
      find.text('Chưa đủ thông tin đáng tin cậy để áp dụng'),
      findsNothing,
    );
  });

  testWidgets('casual response does not show a technical trust banner', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Xin chào',
            response: ChatResponse(
              answer: 'Chào bạn!',
              citations: const [],
              confidence: 1,
              riskLevel: 'low',
              guardrailStatus: 'pass',
              trace: TraceInfo(
                planner: const {
                  'risk_level': 'low',
                  'need_rag': false,
                  'need_weather': false,
                },
                retriever: const {},
                weather: const {},
                reflection: const {},
                guardrail: const {'status': 'pass', 'response_kind': 'casual'},
                research: const {},
                vision: const {},
              ),
            ),
          ),
        ),
      ),
    );

    expect(find.text('Chào bạn!'), findsOneWidget);
    expect(find.text('Đã kiểm tra trước khi phản hồi'), findsNothing);
    expect(
      find.text('Chưa đủ thông tin đáng tin cậy để áp dụng'),
      findsNothing,
    );
  });

  for (final responseKind in const [
    'weather_status',
    'weather_clarification',
    'weather_unavailable',
    'action_status',
    'service_status',
    'refusal',
    'abstention',
    'image_status',
  ]) {
    testWidgets('$responseKind does not show a misleading trust banner', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MessageBubble(
              question: 'Hỏi',
              response: ChatResponse(
                answer: 'Mình cần thêm thông tin hoặc bạn thử lại sau nhé.',
                citations: const [],
                confidence: responseKind == 'action_status' ? 1 : 0,
                riskLevel: 'low',
                guardrailStatus: responseKind == 'action_status'
                    ? 'pass'
                    : 'block',
                trace: TraceInfo(
                  planner: const {},
                  retriever: const {},
                  weather: const {},
                  reflection: const {},
                  guardrail: {'response_kind': responseKind},
                  research: const {},
                  vision: const {},
                ),
              ),
            ),
          ),
        ),
      );

      expect(find.text('Đã kiểm tra trước khi phản hồi'), findsNothing);
      expect(
        find.text('Chưa đủ thông tin đáng tin cậy để áp dụng'),
        findsNothing,
      );
    });
  }

  testWidgets('temporary response offers retry when callback is available', (
    tester,
  ) async {
    var retries = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Thời tiết Đà Lạt hôm nay?',
            response: ChatResponse(
              answer: 'Mình chưa lấy được dự báo lúc này.',
              citations: const [],
              confidence: 1,
              riskLevel: 'low',
              guardrailStatus: 'pass',
              trace: TraceInfo(
                planner: const {},
                retriever: const {},
                weather: const {},
                reflection: const {},
                guardrail: const {'response_kind': 'weather_unavailable'},
                research: const {},
                vision: const {},
              ),
            ),
            onRetry: () => retries++,
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('retry-chat-response')), findsOneWidget);
    await tester.tap(find.byKey(const Key('retry-chat-response')));
    expect(retries, 1);
  });

  testWidgets('weather clarification never offers retry', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Thời tiết thế nào?',
            response: ChatResponse(
              answer: 'Bạn muốn xem thời tiết ở tỉnh nào?',
              citations: const [],
              confidence: 1,
              riskLevel: 'low',
              guardrailStatus: 'pass',
              trace: TraceInfo(
                planner: const {},
                retriever: const {},
                weather: const {},
                reflection: const {},
                guardrail: const {'response_kind': 'weather_clarification'},
                research: const {},
                vision: const {},
              ),
            ),
            onRetry: () {},
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('retry-chat-response')), findsNothing);
  });

  testWidgets('chat error offers a retry action', (tester) async {
    var retries = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Hỏi',
            errorText: 'Phản hồi bị gián đoạn.',
            onRetry: () => retries++,
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('chat-error-card')), findsOneWidget);
    await tester.tap(find.byKey(const Key('retry-chat-message')));
    expect(retries, 1);
  });

  testWidgets('sent attachment names remain visible without retaining bytes', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            question: 'Kiểm tra hai ảnh này',
            imageCount: 2,
            imageNames: ['mat-la.png', 'than-cay.webp'],
            isLoading: true,
          ),
        ),
      ),
    );

    expect(find.text('2 ảnh đã đính kèm'), findsOneWidget);
    expect(find.text('mat-la.png • than-cay.webp'), findsOneWidget);
    expect(find.byType(Image), findsNothing);
  });
}
