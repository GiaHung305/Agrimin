class FarmTask {
  final String id;
  final String title;
  final String? description;
  final DateTime? dueAt;
  final String status;

  const FarmTask({
    required this.id,
    required this.title,
    this.description,
    this.dueAt,
    required this.status,
  });

  factory FarmTask.fromJson(Map<String, dynamic> json) => FarmTask(
        id: json['id'] as String,
        title: json['title'] as String,
        description: json['description'] as String?,
        dueAt: json['due_at'] == null ? null : DateTime.parse(json['due_at'] as String).toLocal(),
        status: json['status'] as String,
      );
}
