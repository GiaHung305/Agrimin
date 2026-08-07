import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

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

  static Future<String?> register(String email, String password) async {
    final response = await http.post(
      Uri.parse("$supabaseUrl/auth/v1/signup"),
      headers: {"apikey": publishableKey, "Content-Type": "application/json"},
      body: jsonEncode({"email": email, "password": password}),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final token = data["access_token"];
      if (token != null) {
        await _storage.write(key: "access_token", value: token);
      }
      return token;
    }
    return null;
  }

  static Future<String?> getToken() async {
    return await _storage.read(key: "access_token");
  }

  static Future<void> logout() async {
    await _storage.delete(key: "access_token");
  }
}
