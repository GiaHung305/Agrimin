class DocumentItem {
  final String id;
  final String title;
  final String? source;
  final String sourceType;
  final double authorityScore;
  final String? version;
  final bool isActive;
  final String ingestedAt;

  DocumentItem({
    required this.id,
    required this.title,
    this.source,
    required this.sourceType,
    required this.authorityScore,
    this.version,
    required this.isActive,
    required this.ingestedAt,
  });

  factory DocumentItem.fromJson(Map<String, dynamic> json) {
    return DocumentItem(
      id: json['id'],
      title: json['title'],
      source: json['source'],
      sourceType: json['source_type'] ?? 'unknown',
      authorityScore: (json['authority_score'] ?? 0.2).toDouble(),
      version: json['version'],
      isActive: json['is_active'] ?? false,
      ingestedAt: json['ingested_at'] ?? '',
    );
  }
}
