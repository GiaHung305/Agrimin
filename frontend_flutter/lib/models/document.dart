class DocumentItem {
  final String id;
  final String title;
  final String? source;
  final String? version;
  final bool isActive;
  final String ingestedAt;

  DocumentItem({
    required this.id,
    required this.title,
    this.source,
    this.version,
    required this.isActive,
    required this.ingestedAt,
  });

  factory DocumentItem.fromJson(Map<String, dynamic> json) {
    return DocumentItem(
      id: json['id'],
      title: json['title'],
      source: json['source'],
      version: json['version'],
      isActive: json['is_active'] ?? false,
      ingestedAt: json['ingested_at'] ?? '',
    );
  }
}