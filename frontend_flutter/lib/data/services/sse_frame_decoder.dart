import 'dart:convert';

/// Incrementally decodes JSON payloads from Server-Sent Events frames.
///
/// Network chunks may split either a frame delimiter or the JSON payload. The
/// decoder therefore keeps incomplete bytes until a complete SSE frame is
/// available and accepts every line ending allowed by the SSE format.
class SseFrameDecoder {
  String _buffer = '';

  List<Map<String, dynamic>> add(String chunk) {
    _buffer += chunk;
    final events = <Map<String, dynamic>>[];

    while (true) {
      final separator = RegExp(r'\r\n\r\n|\n\n|\r\r').firstMatch(_buffer);
      if (separator == null) break;

      final frame = _buffer.substring(0, separator.start);
      _buffer = _buffer.substring(separator.end);
      final event = _decodeFrame(frame);
      if (event != null) events.add(event);
    }
    return events;
  }

  /// Dispatch a final frame when a connection closes without a blank line.
  List<Map<String, dynamic>> close() {
    if (_buffer.trim().isEmpty) {
      _buffer = '';
      return const [];
    }
    final frame = _buffer;
    _buffer = '';
    final event = _decodeFrame(frame);
    return event == null ? const [] : [event];
  }

  Map<String, dynamic>? _decodeFrame(String frame) {
    final data = frame
        .split(RegExp(r'\r\n|\n|\r'))
        .where((line) => line.startsWith('data:'))
        .map((line) => line.substring(5).trimLeft())
        .join('\n');
    if (data.isEmpty) return null;

    final decoded = jsonDecode(data);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('SSE data must be a JSON object');
    }
    return decoded;
  }
}
