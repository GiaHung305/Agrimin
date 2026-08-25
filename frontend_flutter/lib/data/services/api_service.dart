import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/document.dart';
import '../models/chat_image.dart';
import '../models/farm_profile.dart';
import '../models/farm_task.dart';
import '../models/app_notification.dart';
import '../models/farm_monitoring_schedule.dart';
import '../models/farm_plot.dart';
import '../models/user_session.dart';
import '../models/worker_dashboard.dart';
import 'auth_service.dart';
import 'sse_frame_decoder.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => message;
}

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

  static Future<UserSession> getCurrentSession() async {
    Future<http.Response> load(String token) => http.get(
      Uri.parse('$baseUrl/auth/session'),
      headers: {'Authorization': 'Bearer $token'},
    );

    var token = await AuthService.getToken();
    if (token == null) {
      throw const ApiException('Bạn cần đăng nhập lại.', statusCode: 401);
    }
    var response = await load(token);
    if (response.statusCode == 401) {
      token = await AuthService.refreshAccessToken();
      if (token == null) {
        throw const ApiException(
          'Phiên đăng nhập đã hết hạn.',
          statusCode: 401,
        );
      }
      response = await load(token);
    }
    if (response.statusCode != 200) {
      throw ApiException(
        'Không thể xác thực phiên đăng nhập.',
        statusCode: response.statusCode,
      );
    }
    return UserSession.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  static Future<WorkerDashboard> getWorkerDashboard() async {
    final token = await AuthService.getToken();
    if (token == null) {
      throw const ApiException('Bạn cần đăng nhập lại.', statusCode: 401);
    }
    final response = await http.get(
      Uri.parse('$baseUrl/operations/worker-dashboard'),
      headers: {'Authorization': 'Bearer $token'},
    );
    if (response.statusCode != 200) {
      throw ApiException(
        'Không thể tải trạng thái worker.',
        statusCode: response.statusCode,
      );
    }
    return WorkerDashboard.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  static Stream<Map<String, dynamic>> sendMessageStream(
    String question,
    String? conversationId,
    bool deepResearch,
    List<ChatImageAttachment> images,
  ) async* {
    final payload = jsonEncode({
      "question": question,
      "conversation_id": conversationId,
      "deep_research": deepResearch,
      "images": images.map((image) => image.toJson()).toList(),
    });

    Future<http.StreamedResponse> send(String token) {
      final request = http.Request("POST", Uri.parse("$baseUrl/chat/stream"));
      request.headers["Authorization"] = "Bearer $token";
      request.headers["Content-Type"] = "application/json";
      request.body = payload;
      return request.send();
    }

    var token = await AuthService.getToken();
    if (token == null) {
      throw const ApiException('Bạn cần đăng nhập lại.', statusCode: 401);
    }
    var streamedResponse = await send(token);
    if (streamedResponse.statusCode == 401) {
      await streamedResponse.stream.drain<void>();
      token = await AuthService.refreshAccessToken();
      if (token == null) {
        throw const ApiException(
          'Phiên đăng nhập đã hết hạn.',
          statusCode: 401,
        );
      }
      streamedResponse = await send(token);
    }
    if (streamedResponse.statusCode != 200) {
      final body = await utf8.decoder.bind(streamedResponse.stream).join();
      if (streamedResponse.statusCode == 401) {
        throw const ApiException(
          'Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.',
          statusCode: 401,
        );
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

    // A network chunk is not necessarily one SSE event. Decode only complete
    // frames and accept LF, CRLF, or CR delimiters used by SSE transports.
    final decoder = SseFrameDecoder();
    await for (final chunk in streamedResponse.stream.transform(utf8.decoder)) {
      for (final event in decoder.add(chunk)) {
        yield event;
      }
    }
    for (final event in decoder.close()) {
      yield event;
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

  static Future<void> revokeDeviceToken(String token) async {
    final accessToken = await AuthService.getToken();
    if (accessToken == null) return;
    final response = await http.delete(
      Uri.parse(
        '$baseUrl/assistant/device-tokens/${Uri.encodeComponent(token)}',
      ),
      headers: {'Authorization': 'Bearer $accessToken'},
    );
    if (response.statusCode != 200 && response.statusCode != 404) {
      throw ApiException(
        'Không thể thu hồi thiết bị nhận thông báo.',
        statusCode: response.statusCode,
      );
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

  static Future<int> getUnreadNotificationCount() async {
    final token = await AuthService.getToken();
    final response = await http.get(
      Uri.parse("$baseUrl/assistant/notifications/unread-count"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception('Không thể tải số thông báo chưa đọc');
    }
    final data = jsonDecode(utf8.decode(response.bodyBytes));
    return (data['count'] as num?)?.toInt() ?? 0;
  }

  static Future<void> markAllNotificationsRead() async {
    final token = await AuthService.getToken();
    final response = await http.post(
      Uri.parse("$baseUrl/assistant/notifications/read-all"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception('Không thể đánh dấu thông báo đã đọc');
    }
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

  static Future<int> getOpenTaskCount() async {
    final token = await AuthService.getToken();
    final response = await http.get(
      Uri.parse("$baseUrl/assistant/tasks/open-count"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception('Không thể tải số công việc đang mở');
    }
    final data = jsonDecode(utf8.decode(response.bodyBytes));
    return (data['count'] as num?)?.toInt() ?? 0;
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

  static Future<List<FarmMonitoringSchedule>> getMonitoringSchedules() async {
    final token = await AuthService.getToken();
    final response = await http.get(
      Uri.parse("$baseUrl/assistant/monitoring-schedules"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception('Không thể tải lịch theo dõi cây trồng');
    }
    final data = jsonDecode(utf8.decode(response.bodyBytes)) as List<dynamic>;
    return data
        .map(
          (item) =>
              FarmMonitoringSchedule.fromJson(item as Map<String, dynamic>),
        )
        .toList();
  }

  static Future<FarmMonitoringSchedule> createMonitoringSchedule({
    required String cropSeasonId,
    required int frequencyHours,
    required String notificationScope,
  }) async {
    final token = await AuthService.getToken();
    final response = await http.post(
      Uri.parse("$baseUrl/assistant/monitoring-schedules"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode({
        'consent': true,
        'crop_season_id': cropSeasonId,
        'frequency_hours': frequencyHours,
        'notification_scope': notificationScope,
      }),
    );
    if (response.statusCode != 201) {
      throw Exception(_apiDetail(response, 'Không thể bật lịch theo dõi'));
    }
    return FarmMonitoringSchedule.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  static Future<FarmMonitoringSchedule> updateMonitoringSchedule(
    String scheduleId,
    Map<String, dynamic> changes,
  ) async {
    final token = await AuthService.getToken();
    final response = await http.patch(
      Uri.parse("$baseUrl/assistant/monitoring-schedules/$scheduleId"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode(changes),
    );
    if (response.statusCode != 200) {
      throw Exception(_apiDetail(response, 'Không thể cập nhật lịch theo dõi'));
    }
    return FarmMonitoringSchedule.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  static Future<void> deleteMonitoringSchedule(String scheduleId) async {
    final token = await AuthService.getToken();
    final response = await http.delete(
      Uri.parse("$baseUrl/assistant/monitoring-schedules/$scheduleId"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception(_apiDetail(response, 'Không thể xóa lịch theo dõi'));
    }
  }

  static Future<List<FarmPlot>> getFarmPlots() async {
    final token = await AuthService.getToken();
    final response = await http.get(
      Uri.parse("$baseUrl/assistant/plots"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception(_apiDetail(response, 'Không thể tải danh sách thửa đất'));
    }
    final data = jsonDecode(utf8.decode(response.bodyBytes)) as List<dynamic>;
    return data
        .map((item) => FarmPlot.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  static Future<FarmPlot> createFarmPlot({
    required String name,
    double? areaHa,
    String? locationNote,
    double? latitude,
    double? longitude,
    double? elevationM,
    double? locationAccuracyM,
    String? locationSource,
  }) async {
    final token = await AuthService.getToken();
    final response = await http.post(
      Uri.parse("$baseUrl/assistant/plots"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode({
        'name': name,
        'area_ha': areaHa,
        'location_note': locationNote,
        'latitude': latitude,
        'longitude': longitude,
        'elevation_m': elevationM,
        'location_accuracy_m': locationAccuracyM,
        'location_source': locationSource,
      }),
    );
    if (response.statusCode != 201) {
      throw Exception(_apiDetail(response, 'Không thể tạo thửa đất'));
    }
    return FarmPlot.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  static Future<FarmPlot> updateFarmPlot(
    String plotId,
    Map<String, dynamic> changes,
  ) async {
    final token = await AuthService.getToken();
    final response = await http.patch(
      Uri.parse("$baseUrl/assistant/plots/$plotId"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode(changes),
    );
    if (response.statusCode != 200) {
      throw Exception(_apiDetail(response, 'Không thể cập nhật thửa đất'));
    }
    return FarmPlot.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  static Future<void> archiveFarmPlot(String plotId) async {
    final token = await AuthService.getToken();
    final response = await http.delete(
      Uri.parse("$baseUrl/assistant/plots/$plotId"),
      headers: {"Authorization": "Bearer $token"},
    );
    if (response.statusCode != 200) {
      throw Exception(_apiDetail(response, 'Không thể lưu trữ thửa đất'));
    }
  }

  static Future<CropSeason> createCropSeason({
    required String plotId,
    required String crop,
    String? variety,
    String? growthStage,
    DateTime? plantedOn,
    DateTime? expectedHarvestOn,
  }) async {
    final token = await AuthService.getToken();
    final response = await http.post(
      Uri.parse("$baseUrl/assistant/plots/$plotId/seasons"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode({
        'crop': crop,
        'variety': variety,
        'growth_stage': growthStage,
        'planted_on': _dateOnly(plantedOn),
        'expected_harvest_on': _dateOnly(expectedHarvestOn),
        'status': 'active',
      }),
    );
    if (response.statusCode != 201) {
      throw Exception(_apiDetail(response, 'Không thể tạo mùa vụ'));
    }
    return CropSeason.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  static Future<CropSeason> updateCropSeason(
    String seasonId,
    Map<String, dynamic> changes,
  ) async {
    final token = await AuthService.getToken();
    final response = await http.patch(
      Uri.parse("$baseUrl/assistant/seasons/$seasonId"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode(changes),
    );
    if (response.statusCode != 200) {
      throw Exception(_apiDetail(response, 'Không thể cập nhật mùa vụ'));
    }
    return CropSeason.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  static String? _dateOnly(DateTime? value) {
    if (value == null) return null;
    final month = value.month.toString().padLeft(2, '0');
    final day = value.day.toString().padLeft(2, '0');
    return '${value.year}-$month-$day';
  }

  static String _apiDetail(http.Response response, String fallback) {
    try {
      final data = jsonDecode(utf8.decode(response.bodyBytes));
      if (data is Map && data['detail'] != null) {
        return data['detail'].toString();
      }
    } on FormatException {
      // Use the stable Vietnamese fallback for non-JSON server errors.
    }
    return fallback;
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
