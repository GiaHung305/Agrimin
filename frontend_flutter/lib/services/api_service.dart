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

  static Future<List<DocumentItem>> getDocuments() async {
    final response = await http.get(Uri.parse("$baseUrl/documents"));

    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(utf8.decode(response.bodyBytes));
      return data.map((item) => DocumentItem.fromJson(item)).toList();
    } else {
      throw Exception("Lỗi tải danh sách documents: ${response.statusCode}");
    }
  }

  static Future<void> deactivateDocument(String documentId) async {
    final response = await http.patch(
      Uri.parse("$baseUrl/documents/$documentId/deactivate"),
    );
    if (response.statusCode != 200) {
      throw Exception("Lỗi deactivate document: ${response.statusCode}");
    }
  }
}