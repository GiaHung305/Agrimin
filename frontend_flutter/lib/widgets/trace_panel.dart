import 'package:flutter/material.dart';
import '../models/chat_response.dart';

class TracePanel extends StatelessWidget {
  final TraceInfo trace;

  const TracePanel({super.key, required this.trace});

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      leading: const Icon(Icons.psychology_outlined, size: 20),
      title: const Text("Xem AI đã suy nghĩ thế nào", style: TextStyle(fontSize: 13)),
      childrenPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      children: [
        _buildStep(
          icon: "🧠",
          label: "Planner",
          detail: "Mức độ rủi ro: ${trace.planner['risk_level'] ?? 'N/A'}"
              "${trace.planner['need_weather'] == true ? ' • Cần dữ liệu thời tiết' : ''}",
        ),
        _buildStep(
          icon: "🔎",
          label: "Retriever",
          detail: "Tìm thấy ${trace.retriever['docs_found'] ?? 0} tài liệu"
              "${trace.retriever['top_source'] != null ? ' • Nguồn chính: ${trace.retriever['top_source']}' : ''}",
        ),
        if (trace.weather['used'] == true)
          _buildStep(
            icon: "🌤",
            label: "Thời tiết",
            detail: "Đã dùng dữ liệu thời tiết cho ${trace.weather['province'] ?? 'khu vực'}",
          ),
        _buildStep(
          icon: "🔁",
          label: "Reflection",
          detail: "Đánh giá: ${trace.reflection['notes'] ?? 'N/A'}"
              "${(trace.reflection['retry_count'] ?? 0) > 0 ? ' • Đã tìm lại ${trace.reflection['retry_count']} lần' : ''}",
        ),
        _buildStep(
          icon: "🛡",
          label: "Guardrail",
          detail: trace.guardrail['status'] == 'pass'
              ? "Đã kiểm tra an toàn — Độ tin cậy: ${((trace.guardrail['confidence'] ?? 0) * 100).toStringAsFixed(0)}%"
              : "Đã chặn vì chưa đủ nguồn tin cậy",
          color: trace.guardrail['status'] == 'pass' ? Colors.green : Colors.red,
        ),
      ],
    );
  }

  Widget _buildStep({required String icon, required String label, required String detail, Color? color}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(icon, style: const TextStyle(fontSize: 14)),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: color)),
                Text(detail, style: TextStyle(fontSize: 12, color: color ?? Colors.black54)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}