import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:frontend_flutter/data/models/registration_result.dart';

class AuthService {
  static const String supabaseUrl = "https://mofxbgklmfmmkuefavxx.supabase.co";
  static const String publishableKey =
      "sb_publishable_22CDWk-HscssH5ApQ3QThw_URF6fyGq";

  static final _storage = const FlutterSecureStorage();

  static Future<String?> login(String email, String password) async {
    final response = await http.post(
      Uri.parse("$supabaseUrl/auth/v1/token?grant_type=password"),
      headers: {"apikey": publishableKey, "Content-Type": "application/json"},
      body: jsonEncode({"email": email, "password": password}),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final token = data["access_token"];
      await _storage.write(key: "access_token", value: token);
      return token;
    }
    return null;
  }

  static Future<RegistrationResult> register({
    required String email,
    required String password,
    required String displayName,
    http.Client? client,
  }) async {
    final ownsClient = client == null;
    final requestClient = client ?? http.Client();
    try {
      final response = await requestClient.post(
        Uri.parse("$supabaseUrl/auth/v1/signup"),
        headers: {"apikey": publishableKey, "Content-Type": "application/json"},
        body: jsonEncode({
          "email": email,
          "password": password,
          "data": {"display_name": displayName},
        }),
      );

      final data = _decodeObject(response.body);
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final session = data["session"] is Map<String, dynamic>
            ? data["session"] as Map<String, dynamic>
            : const <String, dynamic>{};
        final token = data["access_token"] ?? session["access_token"];
        if (token != null) {
          await _storage.write(key: "access_token", value: token.toString());
          return const RegistrationResult.authenticated();
        }
        if (data["user"] != null) {
          return const RegistrationResult.confirmationRequired();
        }
        return const RegistrationResult.failed(
          'Máy chủ chưa tạo được tài khoản. Vui lòng thử lại.',
        );
      }

      return RegistrationResult.failed(_registrationError(data));
    } finally {
      if (ownsClient) requestClient.close();
    }
  }

  static Map<String, dynamic> _decodeObject(String body) {
    try {
      final decoded = jsonDecode(body);
      return decoded is Map<String, dynamic>
          ? decoded
          : const <String, dynamic>{};
    } catch (_) {
      return const <String, dynamic>{};
    }
  }

  static String _registrationError(Map<String, dynamic> data) {
    final raw = (data["msg"] ?? data["message"] ?? data["error_description"])
        ?.toString()
        .toLowerCase();
    if (raw == null || raw.isEmpty) {
      return 'Không thể tạo tài khoản lúc này. Vui lòng thử lại sau.';
    }
    if (raw.contains('already') || raw.contains('registered')) {
      return 'Email này đã được đăng ký. Bạn hãy đăng nhập nhé.';
    }
    if (raw.contains('password')) {
      return 'Mật khẩu chưa đáp ứng yêu cầu bảo mật.';
    }
    if (raw.contains('email')) {
      return 'Email chưa hợp lệ hoặc chưa thể sử dụng.';
    }
    return 'Không thể tạo tài khoản lúc này. Vui lòng thử lại sau.';
  }

  static Future<String?> getToken() async {
    return await _storage.read(key: "access_token");
  }

  static Future<void> logout() async {
    await _storage.delete(key: "access_token");
  }
}
