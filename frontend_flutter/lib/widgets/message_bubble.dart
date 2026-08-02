import 'package:flutter/material.dart';
import '../models/chat_response.dart';
import 'trace_panel.dart';

class MessageBubble extends StatelessWidget {
  final String question;
  final ChatResponse? response;
  final bool isLoading;
  final String? partialText;

  const MessageBubble({
    super.key,
    required this.question,
    this.response,
    this.isLoading = false,
    this.partialText,
  });

  Color _guardrailColor(String? status) {
    if (status == "block") return Colors.red;
    if (status == "pass") return Colors.green;
    return Colors.grey;
  }

  String _guardrailLabel(String? status) {
    if (status == "block") return "🛡 Đã chặn (thiếu nguồn tin cậy)";
    if (status == "pass") return "🛡 Đã kiểm tra an toàn";
    return "";
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Align(
          alignment: Alignment.centerRight,
          child: Container(
            margin: const EdgeInsets.symmetric(vertical: 4),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.blue.shade100,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(question),
          ),
        ),
        if (response == null && partialText != null && partialText!.isNotEmpty)
          Align(
            alignment: Alignment.centerLeft,
            child: Container(
              margin: const EdgeInsets.symmetric(vertical: 4),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.grey.shade200,
                borderRadius: BorderRadius.circular(12),
              ),
              constraints: const BoxConstraints(maxWidth: 400),
              child: Text(partialText!),
            ),
          )
        else if (isLoading)
          const Padding(
            padding: EdgeInsets.all(12),
            child: Row(
              children: [
                SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                SizedBox(width: 8),
                Text("Đang suy nghĩ..."),
              ],
            ),
          )
        else if (response != null)
          Align(
            alignment: Alignment.centerLeft,
            child: Container(
              margin: const EdgeInsets.symmetric(vertical: 4),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.grey.shade200,
                borderRadius: BorderRadius.circular(12),
              ),
              constraints: const BoxConstraints(maxWidth: 400),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(response!.answer),
                  const SizedBox(height: 8),
                  if (response!.citations.isNotEmpty)
                    Text(
                      "Nguồn: ${response!.citations.join(', ')}",
                      style: const TextStyle(fontSize: 12, color: Colors.black54),
                    ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(
                        Icons.shield,
                        size: 16,
                        color: _guardrailColor(response!.guardrailStatus),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        _guardrailLabel(response!.guardrailStatus),
                        style: TextStyle(
                          fontSize: 12,
                          color: _guardrailColor(response!.guardrailStatus),
                        ),
                      ),
                    ],
                  ),
                  if (response!.trace != null) ...[
                    const SizedBox(height: 4),
                    TracePanel(trace: response!.trace!),
                  ],
                ],
              ),
            ),
          ),
      ],
    );
  }
}