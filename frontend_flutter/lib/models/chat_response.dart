class TraceInfo {
  final Map<String, dynamic> planner;
  final Map<String, dynamic> retriever;
  final Map<String, dynamic> weather;
  final Map<String, dynamic> reflection;
  final Map<String, dynamic> guardrail;

  TraceInfo({
    required this.planner,
    required this.retriever,
    required this.weather,
    required this.reflection,
    required this.guardrail,
  });

  factory TraceInfo.fromJson(Map<String, dynamic> json) {
    return TraceInfo(
      planner: json['planner'] ?? {},
      retriever: json['retriever'] ?? {},
      weather: json['weather'] ?? {},
      reflection: json['reflection'] ?? {},
      guardrail: json['guardrail'] ?? {},
    );
  }
}

class ChatResponse {
  final String answer;
  final List<String> citations;
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
      citations: List<String>.from(json['citations'] ?? []),
      confidence: (json['confidence'] ?? 0.0).toDouble(),
      riskLevel: json['risk_level'] ?? 'low',
      guardrailStatus: json['guardrail_status'],
      trace: json['trace'] != null ? TraceInfo.fromJson(json['trace']) : null,
      conversationId: json['conversation_id'],
      pendingAction: json['pending_action'] is Map ? Map<String, dynamic>.from(json['pending_action']) : null,
    );
  }
}
