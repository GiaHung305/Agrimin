import 'package:flutter_test/flutter_test.dart';
import 'package:frontend_flutter/data/services/sse_frame_decoder.dart';

void main() {
  test('buffers JSON split across network chunks', () {
    final decoder = SseFrameDecoder();

    expect(decoder.add('data: {"type":"chu'), isEmpty);
    expect(decoder.add('nk","payload":"xin chao"}\n\n'), [
      {'type': 'chunk', 'payload': 'xin chao'},
    ]);
    expect(decoder.close(), isEmpty);
  });

  test('accepts CRLF frames and data without an optional space', () {
    final decoder = SseFrameDecoder();

    expect(
      decoder.add('data:{"type":"meta","payload":{"confidence":0.9}}\r'),
      isEmpty,
    );
    expect(decoder.add('\n\r\n'), [
      {
        'type': 'meta',
        'payload': {'confidence': 0.9},
      },
    ]);
  });

  test('decodes multiple frames and ignores comments', () {
    final decoder = SseFrameDecoder();

    expect(
      decoder.add(
        ': keepalive\n\n'
        'data: {"type":"chunk","payload":"a"}\r\r'
        'data: {"type":"chunk","payload":"b"}\n\n',
      ),
      [
        {'type': 'chunk', 'payload': 'a'},
        {'type': 'chunk', 'payload': 'b'},
      ],
    );
  });

  test('dispatches a complete final frame at connection close', () {
    final decoder = SseFrameDecoder();

    expect(decoder.add('data: {"type":"done"}'), isEmpty);
    expect(decoder.close(), [
      {'type': 'done'},
    ]);
  });

  test('rejects non-object JSON payloads', () {
    final decoder = SseFrameDecoder();

    expect(
      () => decoder.add('data: [1,2,3]\n\n'),
      throwsA(isA<FormatException>()),
    );
  });
}
