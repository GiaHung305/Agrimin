class AppNotification {
  const AppNotification({
    required this.id,
    required this.kind,
    required this.title,
    required this.body,
    required this.createdAt,
    this.readAt,
    this.recommendation,
  });

  final String id;
  final String kind;
  final String title;
  final String body;
  final DateTime? createdAt;
  final DateTime? readAt;
  final NotificationRecommendation? recommendation;

  factory AppNotification.fromJson(Map<String, dynamic> json) =>
      AppNotification(
        id: json['id']?.toString() ?? '',
        kind: json['kind']?.toString() ?? 'general',
        title: json['title']?.toString() ?? 'Thông báo AgriMind',
        body: json['body']?.toString() ?? '',
        createdAt: DateTime.tryParse(
          json['created_at']?.toString() ?? '',
        )?.toLocal(),
        readAt: DateTime.tryParse(json['read_at']?.toString() ?? '')?.toLocal(),
        recommendation: json['recommendation'] is Map<String, dynamic>
            ? NotificationRecommendation.fromJson(
                json['recommendation'] as Map<String, dynamic>,
              )
            : null,
      );
}

class NotificationRecommendation {
  const NotificationRecommendation({
    required this.id,
    required this.status,
    required this.pendingActionId,
    this.expiresAt,
  });

  final String id;
  final String status;
  final String pendingActionId;
  final DateTime? expiresAt;

  bool get isPending => status == 'notified' || status == 'proposed';
  bool get isExpired =>
      expiresAt != null && expiresAt!.isBefore(DateTime.now());

  factory NotificationRecommendation.fromJson(Map<String, dynamic> json) =>
      NotificationRecommendation(
        id: json['id']?.toString() ?? '',
        status: json['status']?.toString() ?? '',
        pendingActionId: json['pending_action_id']?.toString() ?? '',
        expiresAt: DateTime.tryParse(
          json['expires_at']?.toString() ?? '',
        )?.toLocal(),
      );
}
