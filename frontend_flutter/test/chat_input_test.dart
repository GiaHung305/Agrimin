import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend_flutter/data/models/chat_image.dart';
import 'package:frontend_flutter/features/assistant/presentation/widgets/chat_input.dart';

void main() {
  final pngBytes = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  );

  Widget buildInput({
    required void Function(
      String text,
      bool deepResearch,
      List<ChatImageAttachment> images,
    )
    onSend,
    bool isLoading = false,
    VoidCallback? onCancel,
    Future<List<ChatImageAttachment>> Function()? pickImages,
  }) => MaterialApp(
    home: Scaffold(
      body: Align(
        alignment: Alignment.bottomCenter,
        child: ChatInput(
          onSend: onSend,
          isLoading: isLoading,
          onCancel: onCancel,
          pickImages: pickImages,
        ),
      ),
    ),
  );

  testWidgets('send stays disabled until the user provides a draft', (
    tester,
  ) async {
    var sends = 0;
    String? sentText;
    await tester.pumpWidget(
      buildInput(
        onSend: (text, _, _) {
          sends++;
          sentText = text;
        },
      ),
    );

    expect(
      tester.widget<InkWell>(find.byKey(const Key('send-chat-message'))).onTap,
      isNull,
    );

    await tester.enterText(find.byType(TextField), '  Lá dứa bị vàng  ');
    await tester.pump();
    expect(
      tester.widget<InkWell>(find.byKey(const Key('send-chat-message'))).onTap,
      isNotNull,
    );

    await tester.tap(find.byKey(const Key('send-chat-message')));
    await tester.pump();
    expect(sends, 1);
    expect(sentText, 'Lá dứa bị vàng');
    expect(find.text('Lá dứa bị vàng'), findsNothing);
  });

  testWidgets('loading state offers an accessible cancel action', (
    tester,
  ) async {
    var cancels = 0;
    await tester.pumpWidget(
      buildInput(
        isLoading: true,
        onCancel: () => cancels++,
        onSend: (_, _, _) {},
      ),
    );

    expect(find.byTooltip('Dừng trả lời'), findsOneWidget);
    expect(find.byKey(const Key('cancel-chat-response')), findsOneWidget);
    expect(find.byKey(const Key('send-chat-message')), findsNothing);

    await tester.tap(find.byKey(const Key('cancel-chat-response')));
    expect(cancels, 1);
  });

  testWidgets('selected image has an accessible preview and can be sent', (
    tester,
  ) async {
    String? sentText;
    List<ChatImageAttachment>? sentImages;
    final attachment = ChatImageAttachment(
      bytes: pngBytes,
      name: 'la-dua.png',
      mimeType: 'image/png',
    );

    await tester.pumpWidget(
      buildInput(
        pickImages: () async => [attachment],
        onSend: (text, _, images) {
          sentText = text;
          sentImages = images;
        },
      ),
    );

    await tester.tap(find.byTooltip('Đính kèm ảnh cây trồng'));
    await tester.pumpAndSettle();

    expect(find.text('la-dua.png'), findsOneWidget);
    expect(find.text('1 KB'), findsOneWidget);
    expect(find.byTooltip('Bỏ ảnh la-dua.png'), findsOneWidget);
    expect(
      tester.widget<Image>(find.byType(Image)).semanticLabel,
      'Ảnh đính kèm la-dua.png',
    );

    await tester.tap(find.byKey(const Key('send-chat-message')));
    await tester.pump();
    expect(sentText, 'Hãy kiểm tra ảnh cây trồng này.');
    expect(sentImages, hasLength(1));
    expect(sentImages!.single.name, 'la-dua.png');
    expect(find.text('la-dua.png'), findsNothing);
  });

  testWidgets('duplicate image is rejected without breaking compact layout', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 640);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    final attachment = ChatImageAttachment(
      bytes: pngBytes,
      name: 'anh-la-dua-ten-rat-dai-de-kiem-tra-man-hinh-hep.png',
      mimeType: 'image/png',
    );
    await tester.pumpWidget(
      buildInput(pickImages: () async => [attachment], onSend: (_, _, _) {}),
    );

    await tester.tap(find.byTooltip('Đính kèm ảnh cây trồng'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Đính kèm ảnh cây trồng'));
    await tester.pump();

    expect(
      find.text('anh-la-dua-ten-rat-dai-de-kiem-tra-man-hinh-hep.png'),
      findsOneWidget,
    );
    expect(find.textContaining('đã được chọn rồi'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
