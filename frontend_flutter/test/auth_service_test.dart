import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:frontend_flutter/data/models/registration_result.dart';
import 'package:frontend_flutter/data/services/auth_service.dart';

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });

  test(
    'register preserves display name and detects email confirmation',
    () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/auth/v1/signup');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['email'], 'an@example.com');
        expect(body['data'], {'display_name': 'Nguyễn Văn An'});
        return http.Response(
          jsonEncode({
            'user': {'id': 'user-1', 'email': 'an@example.com'},
            'session': null,
          }),
          200,
        );
      });

      final result = await AuthService.register(
        email: 'an@example.com',
        password: 'Matkhau@123',
        displayName: 'Nguyễn Văn An',
        client: client,
      );

      expect(result.status, RegistrationStatus.confirmationRequired);
    },
  );

  test('register translates duplicate email into a friendly error', () async {
    final client = MockClient(
      (_) async =>
          http.Response(jsonEncode({'msg': 'User already registered'}), 422),
    );

    final result = await AuthService.register(
      email: 'existing@example.com',
      password: 'Matkhau@123',
      displayName: 'Người dùng cũ',
      client: client,
    );

    expect(result.status, RegistrationStatus.failed);
    expect(result.message, contains('đã được đăng ký'));
  });

  test('login persists a refreshable session', () async {
    final client = MockClient(
      (_) async => http.Response(
        jsonEncode({
          'access_token': 'access-1',
          'refresh_token': 'refresh-1',
          'expires_in': 3600,
        }),
        200,
      ),
    );

    final token = await AuthService.login(
      'an@example.com',
      'Matkhau@123',
      client: client,
    );

    expect(token, 'access-1');
    expect(await AuthService.getToken(), 'access-1');
  });

  test('expired session refreshes without asking the user to login', () async {
    final loginClient = MockClient(
      (_) async => http.Response(
        jsonEncode({
          'access_token': 'access-old',
          'refresh_token': 'refresh-1',
          'expires_in': 1,
        }),
        200,
      ),
    );
    await AuthService.login(
      'an@example.com',
      'Matkhau@123',
      client: loginClient,
    );

    final refreshClient = MockClient((request) async {
      expect(request.url.queryParameters['grant_type'], 'refresh_token');
      return http.Response(
        jsonEncode({
          'access_token': 'access-new',
          'refresh_token': 'refresh-2',
          'expires_in': 3600,
        }),
        200,
      );
    });

    final token = await AuthService.getToken(
      client: refreshClient,
      now: DateTime.now().toUtc().add(const Duration(minutes: 3)),
    );

    expect(token, 'access-new');
  });

  test('password reset requests a Supabase recovery email', () async {
    final client = MockClient((request) async {
      expect(request.url.path, '/auth/v1/recover');
      expect(request.url.queryParameters['redirect_to'], isNotEmpty);
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      expect(body['email'], 'an@example.com');
      return http.Response('{}', 200);
    });

    final error = await AuthService.requestPasswordReset(
      'an@example.com',
      client: client,
    );

    expect(error, isNull);
  });

  test('resend verification uses signup email type', () async {
    final client = MockClient((request) async {
      expect(request.url.path, '/auth/v1/resend');
      expect(request.url.queryParameters['redirect_to'], isNotEmpty);
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      expect(body['type'], 'signup');
      expect(body['email'], 'an@example.com');
      return http.Response('{}', 200);
    });

    final error = await AuthService.resendVerificationEmail(
      'an@example.com',
      client: client,
    );

    expect(error, isNull);
  });

  test(
    'recovery redirect creates a session that can update password',
    () async {
      final consumed = await AuthService.consumeRecoverySession(
        Uri.parse(
          'https://app.example.com/#type=recovery&access_token=recovery-access'
          '&refresh_token=recovery-refresh&expires_in=3600',
        ),
      );
      final client = MockClient((request) async {
        expect(request.method, 'PUT');
        expect(request.url.path, '/auth/v1/user');
        expect(request.headers['Authorization'], 'Bearer recovery-access');
        expect(jsonDecode(request.body), {'password': 'MatkhauMoi@123'});
        return http.Response('{}', 200);
      });

      final error = await AuthService.updatePassword(
        'MatkhauMoi@123',
        client: client,
      );

      expect(consumed, isTrue);
      expect(error, isNull);
    },
  );
}
