import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:frontend_flutter/data/models/auth_session.dart';
import 'package:frontend_flutter/data/models/registration_result.dart';

import 'auth_url_cleanup.dart';

class AuthService {
  static const String supabaseUrl = String.fromEnvironment(
    'SUPABASE_URL',
    defaultValue: 'https://mofxbgklmfmmkuefavxx.supabase.co',
  );
  static const String publishableKey = String.fromEnvironment(
    'SUPABASE_PUBLISHABLE_KEY',
    defaultValue: 'sb_publishable_22CDWk-HscssH5ApQ3QThw_URF6fyGq',
  );
  static const String configuredAuthRedirectUrl = String.fromEnvironment(
    'AUTH_REDIRECT_URL',
  );

  static final _storage = const FlutterSecureStorage();
  static Future<String?>? _refreshInFlight;

  static const _accessTokenKey = 'access_token';
  static const _refreshTokenKey = 'refresh_token';
  static const _expiresAtKey = 'access_token_expires_at';
  static const _refreshWindow = Duration(minutes: 2);

  static Future<String?> login(
    String email,
    String password, {
    http.Client? client,
  }) async {
    final ownsClient = client == null;
    final requestClient = client ?? http.Client();
    try {
      final response = await requestClient.post(
        Uri.parse('$supabaseUrl/auth/v1/token?grant_type=password'),
        headers: {"apikey": publishableKey, "Content-Type": "application/json"},
        body: jsonEncode({"email": email, "password": password}),
      );

      if (response.statusCode == 200) {
        final session = AuthSession.fromSupabase(_decodeObject(response.body));
        await _persistSession(session);
        return session.accessToken;
      }
      return null;
    } finally {
      if (ownsClient) requestClient.close();
    }
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
          "email_redirect_to": authRedirectUrl,
        }),
      );

      final data = _decodeObject(response.body);
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final sessionPayload = data["session"];
        final hasSession =
            data["access_token"] != null ||
            sessionPayload is Map<String, dynamic> &&
                sessionPayload["access_token"] != null;
        if (hasSession) {
          await _persistSession(AuthSession.fromSupabase(data));
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

  static Future<String?> getToken({http.Client? client, DateTime? now}) async {
    String? accessToken;
    String? expiryRaw;
    try {
      accessToken = await _storage.read(key: _accessTokenKey);
      expiryRaw = await _storage.read(key: _expiresAtKey);
    } catch (_) {
      // A fresh or browser-cleared origin may not have the WebCrypto key used
      // by flutter_secure_storage yet. Treat it as signed out so the login
      // screen remains reachable and the first serialized write can initialize
      // storage cleanly.
      return null;
    }
    if (accessToken == null || accessToken.isEmpty) return null;

    final expiresAt = expiryRaw == null ? null : DateTime.tryParse(expiryRaw);
    final currentTime = (now ?? DateTime.now()).toUtc();
    if (expiresAt == null ||
        expiresAt.isAfter(currentTime.add(_refreshWindow))) {
      return accessToken;
    }
    return refreshAccessToken(client: client);
  }

  static Future<String?> refreshAccessToken({http.Client? client}) async {
    if (_refreshInFlight != null) return _refreshInFlight;
    final refresh = _refresh(client: client);
    _refreshInFlight = refresh;
    try {
      return await refresh;
    } finally {
      if (identical(_refreshInFlight, refresh)) _refreshInFlight = null;
    }
  }

  static Future<String?> _refresh({http.Client? client}) async {
    String? refreshToken;
    try {
      refreshToken = await _storage.read(key: _refreshTokenKey);
    } catch (_) {
      return null;
    }
    if (refreshToken == null || refreshToken.isEmpty) {
      await clearLocalSession();
      return null;
    }

    final ownsClient = client == null;
    final requestClient = client ?? http.Client();
    try {
      final response = await requestClient.post(
        Uri.parse('$supabaseUrl/auth/v1/token?grant_type=refresh_token'),
        headers: {'apikey': publishableKey, 'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': refreshToken}),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final session = AuthSession.fromSupabase(_decodeObject(response.body));
        await _persistSession(session, preserveRefreshToken: true);
        return session.accessToken;
      }
      if (response.statusCode == 400 || response.statusCode == 401) {
        await clearLocalSession();
      }
      return null;
    } finally {
      if (ownsClient) requestClient.close();
    }
  }

  static Future<void> _persistSession(
    AuthSession session, {
    bool preserveRefreshToken = false,
  }) async {
    // flutter_secure_storage_web lazily creates its encryption key. Concurrent
    // first writes can race that initialization and leave a newly logged-in
    // browser unable to read its own session. Keep this sequence intentional.
    await _storage.write(key: _accessTokenKey, value: session.accessToken);
    if (session.refreshToken != null) {
      await _storage.write(key: _refreshTokenKey, value: session.refreshToken);
    } else if (!preserveRefreshToken) {
      await _storage.delete(key: _refreshTokenKey);
    }
    if (session.expiresAt != null) {
      await _storage.write(
        key: _expiresAtKey,
        value: session.expiresAt!.toUtc().toIso8601String(),
      );
    } else {
      await _storage.delete(key: _expiresAtKey);
    }
  }

  static Future<void> clearLocalSession() async {
    await _storage.delete(key: _accessTokenKey);
    await _storage.delete(key: _refreshTokenKey);
    await _storage.delete(key: _expiresAtKey);
  }

  static String get authRedirectUrl {
    if (configuredAuthRedirectUrl.isNotEmpty) return configuredAuthRedirectUrl;
    return sanitizedAuthUri(Uri.base).toString();
  }

  static Future<String?> requestPasswordReset(
    String email, {
    http.Client? client,
  }) async {
    final ownsClient = client == null;
    final requestClient = client ?? http.Client();
    try {
      final response = await requestClient.post(
        Uri.parse(
          '$supabaseUrl/auth/v1/recover',
        ).replace(queryParameters: {'redirect_to': authRedirectUrl}),
        headers: {'apikey': publishableKey, 'Content-Type': 'application/json'},
        body: jsonEncode({'email': email}),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) return null;
      return 'Chưa thể gửi email đặt lại mật khẩu. Vui lòng thử lại sau.';
    } finally {
      if (ownsClient) requestClient.close();
    }
  }

  static Future<String?> resendVerificationEmail(
    String email, {
    http.Client? client,
  }) async {
    final ownsClient = client == null;
    final requestClient = client ?? http.Client();
    try {
      final response = await requestClient.post(
        Uri.parse(
          '$supabaseUrl/auth/v1/resend',
        ).replace(queryParameters: {'redirect_to': authRedirectUrl}),
        headers: {'apikey': publishableKey, 'Content-Type': 'application/json'},
        body: jsonEncode({'type': 'signup', 'email': email}),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) return null;
      return 'Chưa thể gửi lại email xác minh. Vui lòng thử lại sau.';
    } finally {
      if (ownsClient) requestClient.close();
    }
  }

  static Future<bool> consumeRecoverySession(Uri uri) async {
    final fragment = uri.fragment.isEmpty
        ? const <String, String>{}
        : Uri.splitQueryString(uri.fragment);
    final parameters = <String, String>{...uri.queryParameters, ...fragment};
    if (parameters['type'] != 'recovery') return false;
    final accessToken = parameters['access_token'];
    if (accessToken == null || accessToken.isEmpty) return false;
    final expiresIn = int.tryParse(parameters['expires_in'] ?? '');
    await _persistSession(
      AuthSession(
        accessToken: accessToken,
        refreshToken: parameters['refresh_token'],
        expiresAt: expiresIn == null
            ? null
            : DateTime.now().toUtc().add(Duration(seconds: expiresIn)),
      ),
    );
    clearAuthCallbackFromAddressBar(uri);
    return true;
  }

  static Future<String?> updatePassword(
    String password, {
    http.Client? client,
  }) async {
    final token = await getToken(client: client);
    if (token == null) return 'Liên kết đặt lại mật khẩu đã hết hạn.';
    final ownsClient = client == null;
    final requestClient = client ?? http.Client();
    try {
      final response = await requestClient.put(
        Uri.parse('$supabaseUrl/auth/v1/user'),
        headers: {
          'apikey': publishableKey,
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({'password': password}),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) return null;
      return 'Chưa thể cập nhật mật khẩu. Liên kết có thể đã hết hạn.';
    } finally {
      if (ownsClient) requestClient.close();
    }
  }

  static Future<void> logout() async {
    try {
      String? token;
      try {
        token = await _storage.read(key: _accessTokenKey);
      } catch (_) {
        // Continue to the authoritative local cleanup below.
      }
      if (token != null) {
        await http
            .post(
              Uri.parse('$supabaseUrl/auth/v1/logout?scope=local'),
              headers: {
                'apikey': publishableKey,
                'Authorization': 'Bearer $token',
              },
            )
            .timeout(const Duration(seconds: 5));
      }
    } catch (_) {
      // Local logout is authoritative for this device. Remote revocation is
      // best effort so a network outage cannot trap the user in the app.
    } finally {
      await clearLocalSession();
    }
  }
}
