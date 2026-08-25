import 'package:flutter_test/flutter_test.dart';
import 'package:frontend_flutter/data/services/auth_url_cleanup.dart';

void main() {
  test('removes recovery query and fragment values from application URL', () {
    final result = sanitizedAuthUri(
      Uri.parse(
        'https://app.agrimind.vn/reset?type=recovery&code=secret'
        '#access_token=secret-token&refresh_token=secret-refresh',
      ),
    );

    expect(result.toString(), 'https://app.agrimind.vn/reset');
    expect(result.query, isEmpty);
    expect(result.fragment, isEmpty);
  });

  test('preserves a non-default local development port', () {
    final result = sanitizedAuthUri(
      Uri.parse('http://localhost:57571/auth#access_token=secret'),
    );

    expect(result.toString(), 'http://localhost:57571/auth');
  });
}
