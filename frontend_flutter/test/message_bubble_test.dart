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
}
