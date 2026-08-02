import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/chat_response.dart';
import '../models/document.dart';
import 'auth_service.dart';

class ApiService {
  static const String baseUrl = "http://localhost:8000/api/v1";

  static Future<ChatResponse> sendMessage(String question, String? conversationId) async {
    final token = await AuthService.getToken();

    final response = await http.post(
      Uri.parse("$baseUrl/chat"),
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": "Bearer $token",
      },
      body: jsonEncode({
        "question": question,
        "conversation_id": conversationId,
      }),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(utf8.decode(response.bodyBytes));
      return ChatResponse.fromJson(data);
    } else if (response.statusCode == 401) {
      throw Exception("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại");
    } else {
      throw Exception("Lỗi server: ${response.statusCode}");
    }
  }

  static Stream<Map<String, dynamic>> sendMessageStream(String question, String? conversationId) async* {
    final token = await AuthService.getToken();
    final request = http.Request("POST", Uri.parse("$baseUrl/chat/stream"));
    request.headers["Authorization"] = "Bearer $token";
    request.headers["Content-Type"] = "application/json";
    request.body = jsonEncode({"question": question, "conversation_id": conversationId});

    final streamedResponse = await request.send();
    final stream = streamedResponse.stream.transform(utf8.decoder);

    await for (final chunk in stream) {
      for (final line in chunk.split("\n")) {
        if (line.startsWith("data: ")) {
          final jsonStr = line.substring(6);
          if (jsonStr.isNotEmpty) {
            yield jsonDecode(jsonStr);
          }
        }
      }
    }
  }

  static Future<List<DocumentItem>> getDocuments() async {
    final token = await AuthService.getToken();
    final response = await http.get(
      Uri.parse("$baseUrl/documents"),
      headers: {"Authorization": "Bearer $token"},
    );

    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(utf8.decode(response.bodyBytes));
      return data.map((item) => DocumentItem.fromJson(item)).toList();
    } else {
      throw Exception("Lỗi tải danh sách documents: ${response.statusCode}");
    }
  }

  static Future<void> deactivateDocument(String documentId) async {
    final token = await AuthService.getToken();
    final response = await http.patch(
      Uri.parse("$baseUrl/documents/$documentId/deactivate"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception("Lỗi deactivate document: ${response.statusCode}");
    }
  }

  static Future<Map<String, dynamic>> uploadDocument({
    required List<int> fileBytes,
    required String fileName,
    required String title,
    String? source,
    String? version,
  }) async {
    final token = await AuthService.getToken();
    final uri = Uri.parse("$baseUrl/documents/upload");
    final request = http.MultipartRequest("POST", uri);

    request.headers["Authorization"] = "Bearer $token";
    request.fields["title"] = title;
    if (source != null) request.fields["source"] = source;
    if (version != null) request.fields["version"] = version;

    request.files.add(
      http.MultipartFile.fromBytes("file", fileBytes, filename: fileName),
    );

    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      return jsonDecode(utf8.decode(response.bodyBytes));
    } else {
      throw Exception("Lỗi upload: ${response.statusCode}");
    }
  }
}