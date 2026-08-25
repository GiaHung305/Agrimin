class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresAt,
  });

  final String accessToken;
  final String? refreshToken;
  final DateTime? expiresAt;

  bool expiresWithin(Duration duration, DateTime now) =>
      expiresAt != null && !expiresAt!.isAfter(now.add(duration));

  factory AuthSession.fromSupabase(Map<String, dynamic> payload) {
    final nested = payload['session'];
    final source = nested is Map<String, dynamic> ? nested : payload;
    final accessToken = source['access_token']?.toString();
    if (accessToken == null || accessToken.isEmpty) {
      throw const FormatException('Missing access token');
    }

    DateTime? expiresAt;
    final expiresAtSeconds = source['expires_at'];
    if (expiresAtSeconds is num) {
      expiresAt = DateTime.fromMillisecondsSinceEpoch(
        expiresAtSeconds.toInt() * 1000,
        isUtc: true,
      );
    } else {
      final expiresIn = source['expires_in'];
      if (expiresIn is num) {
        expiresAt = DateTime.now().toUtc().add(
          Duration(seconds: expiresIn.toInt()),
        );
      }
    }

    return AuthSession(
      accessToken: accessToken,
      refreshToken: source['refresh_token']?.toString(),
      expiresAt: expiresAt,
    );
  }
}
