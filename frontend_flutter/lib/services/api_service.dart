import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/document.dart';
import '../models/chat_image.dart';
import '../models/farm_profile.dart';
import '../models/farm_task.dart';
import '../models/app_notification.dart';
import 'auth_service.dart';

class ApiService {
  static String get baseUrl {
    const configuredUrl = String.fromEnvironment("API_BASE_URL");
    if (configuredUrl.isNotEmpty) return configuredUrl;
    // Android emulators access the development host through 10.0.2.2;
    // localhost would point back to the emulator itself.
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return "http://10.0.2.2:8000/api/v1";
    }
    return "http://localhost:8000/api/v1";
  }

  static Stream<Map<String, dynamic>> sendMessageStream(
    String question,
    String? conversationId,
    bool deepResearch,
    List<ChatImageAttachment> images,
  ) async* {
    final token = await AuthService.getToken();
    final request = http.Request("POST", Uri.parse("$baseUrl/chat/stream"));
    request.headers["Authorization"] = "Bearer $token";
    request.headers["Content-Type"] = "application/json";
    request.body = jsonEncode({
      "question": question,
      "conversation_id": conversationId,
      "deep_research": deepResearch,
      "images": images.map((image) => image.toJson()).toList(),
    });

    final streamedResponse = await request.send();
    if (streamedResponse.statusCode != 200) {
      final body = await utf8.decoder.bind(streamedResponse.stream).join();
      if (streamedResponse.statusCode == 401) {
        throw Exception("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại");
      }
      try {
        final payload = jsonDecode(body) as Map<String, dynamic>;
        final detail = payload['detail']?.toString();
        if (detail != null && detail.isNotEmpty) throw Exception(detail);
      } on FormatException {
        // Fall through to the status-based error when the body is not JSON.
      }
      throw Exception("Lỗi server: ${streamedResponse.statusCode}");
    }

    // A network chunk is not necessarily one SSE event. Buffer until the SSE
    // frame delimiter so partial JSON never reaches jsonDecode.
    String buffer = "";
    await for (final chunk in streamedResponse.stream.transform(utf8.decoder)) {
      buffer += chunk;
      while (true) {
        final separatorIndex = buffer.indexOf("\n\n");
        if (separatorIndex < 0) break;

        final frame = buffer.substring(0, separatorIndex);
        buffer = buffer.substring(separatorIndex + 2);
        final data = frame
            .split("\n")
            .where((line) => line.startsWith("data: "))
            .map((line) => line.substring(6))
            .join("\n");
        if (data.isNotEmpty) {
          yield jsonDecode(data) as Map<String, dynamic>;
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

  static Future<void> resolveAssistantAction(
    String actionId,
    bool confirmed,
  ) async {
    final token = await AuthService.getToken();
    final verb = confirmed ? "confirm" : "cancel";
    final response = await http.post(
      Uri.parse("$baseUrl/assistant/actions/$actionId/$verb"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception("Không thể cập nhật đề xuất của trợ lý");
    }
  }

  static Future<void> registerDeviceToken(String token) async {
    final accessToken = await AuthService.getToken();
    final response = await http.post(
      Uri.parse("$baseUrl/assistant/device-tokens"),
      headers: {
        "Authorization": "Bearer $accessToken",
        "Content-Type": "application/json",
      },
      body: jsonEncode({"token": token, "platform": "android"}),
    );
    if (response.statusCode != 200) {
      throw Exception("Không thể đăng ký thiết bị nhận thông báo");
    }
  }

  static Future<FarmProfile?> getFarmProfile() async {
    final token = await AuthService.getToken();
    final response = await http.get(
      Uri.parse("$baseUrl/assistant/farm-profile"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception('Không thể tải hồ sơ nông trại');
    }
    final dynamic data = jsonDecode(utf8.decode(response.bodyBytes));
    if (data == null) return null;
    return FarmProfile.fromJson(data as Map<String, dynamic>);
  }

  static Future<FarmProfile> saveFarmProfile({
    required String name,
    String? province,
    String? crop,
    double? areaHa,
    String? farmingStyle,
  }) async {
    final token = await AuthService.getToken();
    final response = await http.put(
      Uri.parse("$baseUrl/assistant/farm-profile"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode({
        'name': name,
        'province': province,
        'crop': crop,
        'area_ha': areaHa,
        'farming_style': farmingStyle,
      }),
    );
    if (response.statusCode != 200) {
      throw Exception('Không thể lưu hồ sơ nông trại');
    }
    return FarmProfile.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  static Future<List<AppNotification>> getNotifications() async {
    final token = await AuthService.getToken();
    final response = await http.get(
      Uri.parse("$baseUrl/assistant/notifications"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception('Không thể tải thông báo');
    }
    final data = jsonDecode(utf8.decode(response.bodyBytes)) as List<dynamic>;
    return data
        .map((item) => AppNotification.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  static Future<List<FarmTask>> getTasks() async {
    final token = await AuthService.getToken();
    final response = await http.get(
      Uri.parse("$baseUrl/assistant/tasks"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception("Không thể tải danh sách công việc");
    }
    final data = jsonDecode(utf8.decode(response.bodyBytes)) as List<dynamic>;
    return data
        .map((item) => FarmTask.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  static Future<FarmTask> updateTask(
    String taskId,
    Map<String, dynamic> changes,
  ) async {
    final token = await AuthService.getToken();
    final response = await http.patch(
      Uri.parse("$baseUrl/assistant/tasks/$taskId"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode(changes),
    );
    if (response.statusCode != 200) {
      throw Exception("Không thể cập nhật công việc");
    }
    return FarmTask.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  static Future<void> deleteTask(String taskId) async {
    final token = await AuthService.getToken();
    final response = await http.delete(
      Uri.parse("$baseUrl/assistant/tasks/$taskId"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception("Không thể xóa công việc");
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

  static Future<void> updateDocumentSourceType(
    String documentId,
    String sourceType,
  ) async {
    final token = await AuthService.getToken();
    final response = await http.patch(
      Uri.parse("$baseUrl/documents/$documentId/source-type"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode({"source_type": sourceType}),
    );
    if (response.statusCode != 200) {
      throw Exception("Lỗi phân loại nguồn: ${response.statusCode}");
    }
  }

  static Future<Map<String, dynamic>> uploadDocument({
    required List<int> fileBytes,
    required String fileName,
    required String title,
    String? source,
    String sourceType = 'user_upload',
    String? version,
  }) async {
    final token = await AuthService.getToken();
    final uri = Uri.parse("$baseUrl/documents/upload");
    final request = http.MultipartRequest("POST", uri);

    request.headers["Authorization"] = "Bearer $token";
    request.fields["title"] = title;
    if (source != null) request.fields["source"] = source;
    request.fields["source_type"] = sourceType;
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
