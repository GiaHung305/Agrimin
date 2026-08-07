import 'package:flutter/material.dart';

import '../models/chat_response.dart';
import '../theme/app_theme.dart';
import 'trace_panel.dart';

class MessageBubble extends StatelessWidget {
  final String question;
  final int imageCount;
  final ChatResponse? response;
  final bool isLoading;
  final String? partialText;
  final Future<void> Function(String actionId, bool confirmed)? onResolveAction;

  const MessageBubble({
    super.key,
    required this.question,
    this.imageCount = 0,
    this.response,
    this.isLoading = false,
    this.partialText,
    this.onResolveAction,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: Alignment.centerRight,
          child: Container(
            constraints: const BoxConstraints(maxWidth: 340),
            margin: const EdgeInsets.only(top: 8, bottom: 14),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: const BoxDecoration(
              color: AppColors.forest,
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(18),
                topRight: Radius.circular(5),
                bottomLeft: Radius.circular(18),
                bottomRight: Radius.circular(18),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (imageCount > 0) ...[
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.photo_outlined,
                        size: 16,
                        color: Colors.white,
                      ),
                      const SizedBox(width: 5),
                      Text(
                        '$imageCount ảnh đã đính kèm',
                        style: const TextStyle(
                          color: Colors.white70,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 7),
                ],
                Text(
                  question,
                  style: const TextStyle(color: Colors.white, height: 1.35),
                ),
              ],
            ),
          ),
        ),
        if (response == null && partialText != null && partialText!.isNotEmpty)
          _AssistantCard(
            child: Text(partialText!, style: const TextStyle(height: 1.5)),
          )
        else if (isLoading)
          const _AssistantCard(child: _ThinkingIndicator())
        else if (response != null)
          _AssistantCard(
            child: _ResponseContent(
              response: response!,
              onResolveAction: onResolveAction,
            ),
          ),
      ],
    );
  }
}

class _AssistantCard extends StatelessWidget {
  final Widget child;

  const _AssistantCard({required this.child});

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Container(
        width: 32,
        height: 32,
        margin: const EdgeInsets.only(top: 3, right: 9),
        decoration: const BoxDecoration(
          color: AppColors.mint,
          shape: BoxShape.circle,
        ),
        child: const Icon(Icons.spa_rounded, size: 18, color: AppColors.forest),
      ),
      Expanded(
        child: Container(
          margin: const EdgeInsets.only(bottom: 16),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(5),
              topRight: Radius.circular(20),
              bottomLeft: Radius.circular(20),
              bottomRight: Radius.circular(20),
            ),
            border: Border.all(color: AppColors.line),
          ),
          child: child,
        ),
      ),
    ],
  );
}

class _ThinkingIndicator extends StatelessWidget {
  const _ThinkingIndicator();

  @override
  Widget build(BuildContext context) => const Row(
    children: [
      SizedBox(
        width: 18,
        height: 18,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          color: AppColors.forest,
        ),
      ),
      SizedBox(width: 11),
      Text('AgriMind đang xem xét…', style: TextStyle(color: AppColors.muted)),
    ],
  );
}

class _ResponseContent extends StatelessWidget {
  final ChatResponse response;
  final Future<void> Function(String actionId, bool confirmed)? onResolveAction;

  const _ResponseContent({required this.response, this.onResolveAction});

  @override
  Widget build(BuildContext context) {
    final safe = response.guardrailStatus == 'pass';
    final action = response.pendingAction;
    final citedIds = RegExp(r'\[E\d+\]', caseSensitive: false)
        .allMatches(response.answer)
        .map((match) {
          final marker = match.group(0)!;
          return marker.substring(1, marker.length - 1).toUpperCase();
        })
        .toSet();
    final visibleCitations = citedIds.isEmpty
        ? response.citations.take(3)
        : response.citations.where(
            (citation) => citedIds.contains(citation.citationId?.toUpperCase()),
          );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          response.answer,
          style: const TextStyle(
            color: AppColors.ink,
            height: 1.52,
            fontSize: 15,
          ),
        ),
        if (response.citations.isNotEmpty) ...[
          const SizedBox(height: 14),
          const Text(
            'Nguồn tham khảo',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: AppColors.muted,
            ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: visibleCitations
                .map(
                  (source) => Chip(
                    avatar: Icon(
                      source.url == null
                          ? Icons.description_outlined
                          : Icons.open_in_new_rounded,
                      size: 14,
                      color: AppColors.forest,
                    ),
                    label: Text(
                      source.citationId == null
                          ? source.title
                          : '[${source.citationId}] ${source.title}',
                      overflow: TextOverflow.ellipsis,
                    ),
                    labelStyle: const TextStyle(fontSize: 11),
                    backgroundColor: AppColors.mint,
                    side: BorderSide.none,
                    visualDensity: VisualDensity.compact,
                  ),
                )
                .toList(),
          ),
        ],
        const SizedBox(height: 13),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          decoration: BoxDecoration(
            color: safe ? AppColors.mint : const Color(0xFFFFF4E0),
            borderRadius: BorderRadius.circular(11),
          ),
          child: Row(
            children: [
              Icon(
                safe ? Icons.verified_user_outlined : Icons.info_outline,
                size: 16,
                color: safe ? AppColors.forest : const Color(0xFFB46A00),
              ),
              const SizedBox(width: 7),
              Expanded(
                child: Text(
                  safe
                      ? 'Đã kiểm tra an toàn · Độ tin cậy ${(response.confidence * 100).toStringAsFixed(0)}%'
                      : 'Cần kiểm tra thêm thông tin trước khi áp dụng',
                  style: TextStyle(
                    fontSize: 12,
                    color: safe
                        ? AppColors.forestDark
                        : const Color(0xFF835200),
                  ),
                ),
              ),
            ],
          ),
        ),
        if (response.trace != null) ...[
          const SizedBox(height: 8),
          TracePanel(trace: response.trace!),
        ],
        if (action != null && onResolveAction != null) ...[
          const SizedBox(height: 14),
          _ActionCard(action: action, onResolveAction: onResolveAction!),
        ],
      ],
    );
  }
}

class _ActionCard extends StatelessWidget {
  final Map<String, dynamic> action;
  final Future<void> Function(String actionId, bool confirmed) onResolveAction;

  const _ActionCard({required this.action, required this.onResolveAction});

  @override
  Widget build(BuildContext context) {
    final isTask = action['type'] == 'create_task';
    final payload = action['payload'] as Map<String, dynamic>?;
    final dueAt = payload?['due_at'] as String?;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFFAEC),
        border: Border.all(color: const Color(0xFFF2D996)),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.auto_awesome_rounded,
                color: Color(0xFFC18413),
                size: 19,
              ),
              const SizedBox(width: 7),
              Text(
                isTask ? 'Xác nhận tạo nhắc việc' : 'Xác nhận lưu nhật ký',
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
            ],
          ),
          if (dueAt != null) ...[
            const SizedBox(height: 6),
            Text(
              'Lịch: ${dueAt.replaceFirst('T', ' · ')}',
              style: const TextStyle(fontSize: 12, color: AppColors.muted),
            ),
          ],
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () =>
                      onResolveAction(action['id'] as String, false),
                  child: const Text('Hủy'),
                ),
              ),
              const SizedBox(width: 9),
              Expanded(
                child: FilledButton(
                  onPressed: () =>
                      onResolveAction(action['id'] as String, true),
                  child: const Text('Xác nhận'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
