class TraceInfo {
  final Map<String, dynamic> planner;
  final Map<String, dynamic> retriever;
  final Map<String, dynamic> weather;
  final Map<String, dynamic> reflection;
  final Map<String, dynamic> guardrail;
  final Map<String, dynamic> research;
  final Map<String, dynamic> vision;

  TraceInfo({
    required this.planner,
    required this.retriever,
    required this.weather,
    required this.reflection,
    required this.guardrail,
    required this.research,
    required this.vision,
  });

  factory TraceInfo.fromJson(Map<String, dynamic> json) {
    return TraceInfo(
      planner: json['planner'] ?? {},
      retriever: json['retriever'] ?? {},
      weather: json['weather'] ?? {},
      reflection: json['reflection'] ?? {},
      guardrail: json['guardrail'] ?? {},
      research: json['research'] ?? {},
      vision: json['vision'] ?? {},
    );
  }
}

class ChatResponse {
  final String answer;
  final List<ResearchCitation> citations;
  final double confidence;
  final String riskLevel;
  final String? guardrailStatus;
  final TraceInfo? trace;
  final String? conversationId;
  final Map<String, dynamic>? pendingAction;

  ChatResponse({
    required this.answer,
    required this.citations,
    required this.confidence,
    required this.riskLevel,
    this.guardrailStatus,
    this.trace,
    this.conversationId,
    this.pendingAction,
  });

  factory ChatResponse.fromJson(Map<String, dynamic> json) {
    return ChatResponse(
      answer: json['answer'] ?? '',
      citations: (json['citations'] as List<dynamic>? ?? const [])
          .map(ResearchCitation.fromJson)
          .toList(),
      confidence: (json['confidence'] ?? 0.0).toDouble(),
      riskLevel: json['risk_level'] ?? 'low',
      guardrailStatus: json['guardrail_status'],
      trace: json['trace'] != null ? TraceInfo.fromJson(json['trace']) : null,
      conversationId: json['conversation_id'],
      pendingAction: json['pending_action'] is Map
          ? Map<String, dynamic>.from(json['pending_action'])
          : null,
    );
  }
}

class ResearchCitation {
  final String? citationId;
  final String title;
  final String? url;
  final String type;
  final String sourceType;
  final double authorityScore;

  const ResearchCitation({
    this.citationId,
    required this.title,
    this.url,
    required this.type,
    this.sourceType = 'unknown',
    this.authorityScore = 0.2,
  });

  factory ResearchCitation.fromJson(dynamic json) {
    if (json is String) {
      return ResearchCitation(title: json, type: 'internal');
    }
    final source = json as Map<String, dynamic>;
    return ResearchCitation(
      citationId: source['citation_id']?.toString(),
      title: source['title']?.toString() ?? 'Nguồn tham khảo',
      url: source['url']?.toString(),
      type: source['type']?.toString() ?? 'internal',
      sourceType: source['source_type']?.toString() ?? 'unknown',
      authorityScore: (source['authority_score'] ?? 0.2).toDouble(),
    );
  }
}
