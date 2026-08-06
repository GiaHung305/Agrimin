import 'package:flutter/material.dart';

import '../models/chat_response.dart';
import '../theme/app_theme.dart';

class TracePanel extends StatelessWidget {
  final TraceInfo trace;

  const TracePanel({super.key, required this.trace});

  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(
          color: AppColors.background,
          borderRadius: BorderRadius.circular(13),
          border: Border.all(color: AppColors.line),
        ),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 12),
          childrenPadding: const EdgeInsets.fromLTRB(13, 0, 13, 12),
          shape: const Border(),
          collapsedShape: const Border(),
          leading: const Icon(Icons.psychology_alt_outlined, size: 19, color: AppColors.forest),
          title: const Text('Cách AgriMind phân tích', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
          children: [
            _step(Icons.alt_route_rounded, 'Kế hoạch', 'Rủi ro: ${trace.planner['risk_level'] ?? 'thấp'}'),
            _step(Icons.menu_book_outlined, 'Kiến thức', 'Tìm thấy ${trace.retriever['docs_found'] ?? 0} tài liệu liên quan'),
            if (trace.weather['used'] == true)
              _step(Icons.cloud_outlined, 'Thời tiết', 'Đã dùng dự báo cho ${trace.weather['province'] ?? 'khu vực của bạn'}'),
            _step(Icons.verified_outlined, 'Kiểm tra an toàn',
                trace.guardrail['status'] == 'pass' ? 'Đủ điều kiện phản hồi' : 'Cần thêm dữ liệu đáng tin cậy'),
          ],
        ),
      );

  Widget _step(IconData icon, String title, String detail) => Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, size: 16, color: AppColors.forest),
          const SizedBox(width: 9),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
            const SizedBox(height: 2),
            Text(detail, style: const TextStyle(fontSize: 12, color: AppColors.muted)),
          ])),
        ]),
      );
}
