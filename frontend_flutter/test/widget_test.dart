import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend_flutter/main.dart';

void main() {
  testWidgets('AgriMind AI app renders chat screen', (WidgetTester tester) async {
    await tester.pumpWidget(const AgriMindApp());

    // Xác nhận tiêu đề app hiển thị đúng
    expect(find.text('AgriMind AI'), findsOneWidget);
  });
}