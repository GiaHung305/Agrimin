import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:frontend_flutter/data/models/registration_result.dart';
import 'package:frontend_flutter/data/services/auth_service.dart';

void main() {
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
}
