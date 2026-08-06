class AppNotification {
  const AppNotification({
    required this.id,
    required this.kind,
    required this.title,
    required this.body,
    required this.createdAt,
    this.readAt,
  });

  final String id;
  final String kind;
  final String title;
  final String body;
  final DateTime? createdAt;
  final DateTime? readAt;

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
      );
}
