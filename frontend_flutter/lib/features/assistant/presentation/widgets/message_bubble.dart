import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:frontend_flutter/data/models/chat_response.dart';
import 'package:frontend_flutter/design_system/design_system.dart';

typedef SourceUrlLauncher = Future<bool> Function(Uri uri);

Uri? safeSourceUri(String? value) {
  final uri = Uri.tryParse(value?.trim() ?? '');
  final scheme = uri?.scheme.toLowerCase();
  if (uri == null ||
      !const {'http', 'https'}.contains(scheme) ||
      uri.host.trim().isEmpty ||
      uri.userInfo.isNotEmpty) {
    return null;
  }
  return uri;
}

Future<bool> _launchSourceUrl(Uri uri) =>
    launchUrl(uri, mode: LaunchMode.externalApplication);

class MessageBubble extends StatelessWidget {
  final String question;
  final int imageCount;
  final List<String> imageNames;
  final ChatResponse? response;
  final bool isLoading;
  final String? partialText;
  final String? progressText;
  final String? errorText;
  final VoidCallback? onRetry;
  final SourceUrlLauncher? launchSourceUrl;
  final Future<void> Function(String actionId, bool confirmed)? onResolveAction;

  const MessageBubble({
    super.key,
    required this.question,
    this.imageCount = 0,
    this.imageNames = const [],
    this.response,
    this.isLoading = false,
    this.partialText,
    this.progressText,
    this.errorText,
    this.onRetry,
    this.launchSourceUrl,
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
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
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
                        color: AppColors.onPrimary,
                      ),
                      const SizedBox(width: 5),
                      Text(
                        '$imageCount ảnh đã đính kèm',
                        style: const TextStyle(
                          color: AppColors.onPrimaryMuted,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                  if (imageNames.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      imageNames.join(' • '),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: AppColors.onPrimaryMuted,
                        fontSize: 11,
                      ),
                    ),
                  ],
                  const SizedBox(height: 7),
                ],
                Text(
                  question,
                  style: const TextStyle(
                    color: AppColors.onPrimary,
                    height: 1.35,
                  ),
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
          _AssistantCard(
            child: _ThinkingIndicator(
              message: progressText ?? 'AgriMind đang xem xét…',
            ),
          )
        else if (errorText != null)
          _AssistantCard(
            child: _AssistantError(message: errorText!, onRetry: onRetry),
          )
        else if (response != null)
          _AssistantCard(
            child: _ResponseContent(
              response: response!,
              onRetry: onRetry,
              launchSourceUrl: launchSourceUrl,
              onResolveAction: onResolveAction,
            ),
          ),
      ],
    );
  }
}

class _AssistantError extends StatelessWidget {
  final String message;
  final VoidCallback? onRetry;

  const _AssistantError({required this.message, this.onRetry});

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Container(
      key: const Key('chat-error-card'),
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: AppColors.dangerSurface,
        borderRadius: BorderRadius.circular(AppRadius.input),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.wifi_off_rounded, size: 18, color: AppColors.danger),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Chưa nhận được câu trả lời',
                  style: TextStyle(
                    color: AppColors.dangerDark,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            message,
            style: const TextStyle(color: AppColors.dangerDark, height: 1.4),
          ),
          if (onRetry != null) ...[
            const SizedBox(height: AppSpacing.xs),
            TextButton.icon(
              key: const Key('retry-chat-message'),
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Thử lại'),
            ),
          ],
        ],
      ),
    ),
  );
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
          margin: const EdgeInsets.only(bottom: AppSpacing.md),
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: BoxDecoration(
            color: AppColors.surface,
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
  final String message;

  const _ThinkingIndicator({required this.message});

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Row(
      children: [
        const SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: AppColors.forest,
          ),
        ),
        const SizedBox(width: 11),
        Expanded(
          child: Text(message, style: const TextStyle(color: AppColors.muted)),
        ),
      ],
    ),
  );
}

class _ResponseContent extends StatelessWidget {
  final ChatResponse response;
  final VoidCallback? onRetry;
  final SourceUrlLauncher? launchSourceUrl;
  final Future<void> Function(String actionId, bool confirmed)? onResolveAction;

  const _ResponseContent({
    required this.response,
    this.onRetry,
    this.launchSourceUrl,
    this.onResolveAction,
  });

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
    final candidateCitations = citedIds.isEmpty
        ? response.citations.take(3).toList()
        : response.citations
              .where(
                (citation) =>
                    citedIds.contains(citation.citationId?.toUpperCase()),
              )
              .toList();
    final citationKeys = <String>{};
    final visibleCitations = candidateCitations.where((citation) {
      final citationId = citation.citationId?.trim().toUpperCase();
      final key = citationId != null && citationId.isNotEmpty
          ? 'id:$citationId'
          : 'source:${citation.title.trim()}|${citation.url?.trim() ?? ''}';
      return citationKeys.add(key);
    }).toList();
    final hasDuplicateCitationMetadata =
        visibleCitations.length != candidateCitations.length;
    final resolvedCitationIds = visibleCitations
        .map((citation) => citation.citationId?.toUpperCase())
        .whereType<String>()
        .toSet();
    final citationsComplete =
        !hasDuplicateCitationMetadata &&
        (citedIds.isEmpty
            ? response.citations.isEmpty
            : citedIds.every(resolvedCitationIds.contains));
    final trustedConfidence =
        response.confidence.isFinite && response.confidence >= 0.70;
    final verified = safe && trustedConfidence && citationsComplete;
    final responseKind = response.trace?.guardrail['response_kind'];
    const statusOnlyResponseKinds = {
      'casual',
      'weather_status',
      'weather_clarification',
      'weather_unavailable',
      'action_status',
      'service_status',
      'refusal',
      'abstention',
      'image_status',
    };
    const retryableResponseKinds = {'weather_unavailable', 'service_status'};
    final showTrustStatus =
        !statusOnlyResponseKinds.contains(responseKind) &&
        (visibleCitations.isNotEmpty || !verified);
    final showRetry =
        onRetry != null && retryableResponseKinds.contains(responseKind);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        MarkdownBody(
          data: response.answer,
          softLineBreak: true,
          styleSheet: MarkdownStyleSheet(
            p: const TextStyle(
              color: AppColors.ink,
              height: 1.52,
              fontSize: 15,
            ),
            strong: const TextStyle(
              color: AppColors.ink,
              fontWeight: FontWeight.w800,
            ),
            listBullet: const TextStyle(
              color: AppColors.forest,
              height: 1.52,
              fontSize: 15,
            ),
            blockSpacing: AppSpacing.sm,
          ),
        ),
        if (visibleCitations.isNotEmpty) ...[
          const SizedBox(height: 14),
          _SourcesSection(
            sources: visibleCitations,
            explicitlyCited: citedIds.isNotEmpty,
            launchSourceUrl: launchSourceUrl,
          ),
        ],
        if (showTrustStatus) ...[
          const SizedBox(height: 13),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              color: verified ? AppColors.mint : AppColors.warningSurfaceStrong,
              borderRadius: BorderRadius.circular(11),
            ),
            child: Row(
              children: [
                Icon(
                  verified ? Icons.verified_outlined : Icons.info_outline,
                  size: 16,
                  color: verified ? AppColors.forest : AppColors.warning,
                ),
                const SizedBox(width: 7),
                Expanded(
                  child: Text(
                    verified
                        ? 'Đã đối chiếu với ${visibleCitations.length} nguồn'
                        : 'Chưa đủ thông tin đáng tin cậy để áp dụng',
                    style: TextStyle(
                      fontSize: 12,
                      color: verified
                          ? AppColors.forestDark
                          : AppColors.warningDark,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
        if (showRetry) ...[
          const SizedBox(height: AppSpacing.xs),
          OutlinedButton.icon(
            key: const Key('retry-chat-response'),
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded, size: 18),
            label: const Text('Thử lại'),
          ),
        ],
        if (action != null && onResolveAction != null) ...[
          const SizedBox(height: 14),
          _ActionCard(action: action, onResolveAction: onResolveAction!),
        ],
      ],
    );
  }
}

class _SourcesSection extends StatelessWidget {
  final List<ResearchCitation> sources;
  final bool explicitlyCited;
  final SourceUrlLauncher? launchSourceUrl;

  const _SourcesSection({
    required this.sources,
    required this.explicitlyCited,
    this.launchSourceUrl,
  });

  @override
  Widget build(BuildContext context) => Container(
    key: const Key('chat-sources-section'),
    decoration: BoxDecoration(
      color: AppColors.background,
      borderRadius: BorderRadius.circular(AppRadius.input),
      border: Border.all(color: AppColors.line),
    ),
    child: ExpansionTile(
      tilePadding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      childrenPadding: const EdgeInsets.only(bottom: AppSpacing.xs),
      shape: const Border(),
      collapsedShape: const Border(),
      leading: const Icon(
        Icons.menu_book_outlined,
        size: 19,
        color: AppColors.forest,
      ),
      title: Text(
        '${explicitlyCited ? 'Nguồn đã dùng' : 'Nguồn tham khảo'} '
        '(${sources.length})',
        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
      ),
      children: sources.map((source) => _sourceTile(context, source)).toList(),
    ),
  );

  Widget _sourceTile(BuildContext context, ResearchCitation source) {
    final sourceUri = safeSourceUri(source.url);
    return ListTile(
      dense: true,
      leading: CircleAvatar(
        radius: 14,
        backgroundColor: AppColors.mint,
        child: Text(
          source.citationId ?? '•',
          style: const TextStyle(
            color: AppColors.forestDark,
            fontSize: 10,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
      title: Text(source.title, style: const TextStyle(fontSize: 12)),
      trailing: sourceUri == null
          ? null
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  tooltip: 'Mở nguồn',
                  icon: const Icon(Icons.open_in_new_rounded, size: 17),
                  onPressed: () async {
                    var opened = false;
                    try {
                      opened = await (launchSourceUrl ?? _launchSourceUrl)(
                        sourceUri,
                      );
                    } catch (_) {
                      opened = false;
                    }
                    if (!context.mounted) return;
                    if (!opened) {
                      AppSnackbar.error(
                        context,
                        'Không thể mở liên kết nguồn. Bạn có thể sao chép để xem sau.',
                      );
                    }
                  },
                ),
                IconButton(
                  tooltip: 'Sao chép liên kết nguồn',
                  icon: const Icon(Icons.copy_rounded, size: 17),
                  onPressed: () async {
                    await Clipboard.setData(
                      ClipboardData(text: sourceUri.toString()),
                    );
                    if (!context.mounted) return;
                    AppSnackbar.success(context, 'Đã sao chép liên kết nguồn.');
                  },
                ),
              ],
            ),
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
        color: AppColors.warningSurface,
        border: Border.all(color: AppColors.warningBorder),
        borderRadius: BorderRadius.circular(AppRadius.input),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.auto_awesome_rounded,
                color: AppColors.warning,
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
          const SizedBox(height: AppSpacing.sm),
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
