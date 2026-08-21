import 'dart:convert';
import 'dart:typed_data';

class ChatImageAttachment {
  final Uint8List bytes;
  final String name;
  final String mimeType;

  const ChatImageAttachment({
    required this.bytes,
    required this.name,
    required this.mimeType,
  });

  Map<String, dynamic> toJson() => {
    'mime_type': mimeType,
    'data_base64': base64Encode(bytes),
  };
}
