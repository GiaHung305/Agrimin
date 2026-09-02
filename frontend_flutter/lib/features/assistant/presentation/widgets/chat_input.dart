import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import 'package:frontend_flutter/data/models/chat_image.dart';
import 'package:frontend_flutter/design_system/design_system.dart';

typedef ChatImagePicker = Future<List<ChatImageAttachment>> Function();

class ChatInput extends StatefulWidget {
  final void Function(
    String text,
    bool deepResearch,
    List<ChatImageAttachment> images,
  )
  onSend;
  final bool isLoading;
  final VoidCallback? onCancel;
  final ChatImagePicker? pickImages;

  const ChatInput({
    super.key,
    required this.onSend,
    required this.isLoading,
    this.onCancel,
    this.pickImages,
  });

  @override
  State<ChatInput> createState() => _ChatInputState();
}

class _ChatInputState extends State<ChatInput> {
  static const bool _deepResearchAvailable = bool.fromEnvironment(
    'ENABLE_DEEP_RESEARCH',
    defaultValue: false,
  );
  static const int _maxImages = 2;
  static const int _maxImageBytes = 4 * 1024 * 1024;
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  final List<ChatImageAttachment> _images = [];
  bool _deepResearch = false;

  bool get _hasDraft =>
      _controller.text.trim().isNotEmpty || _images.isNotEmpty;

  bool get _canSend => !widget.isLoading && _hasDraft;

  @override
  void didUpdateWidget(covariant ChatInput oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Disabling TextField during an SSE request makes Flutter Web drop focus.
    // Restore it when the request finishes so the next prompt can be typed
    // without refreshing the page.
    if (oldWidget.isLoading && !widget.isLoading) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _focusNode.requestFocus();
      });
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  String? _mimeTypeFor(String name) {
    final extension = name.split('.').last.toLowerCase();
    return switch (extension) {
      'jpg' || 'jpeg' => 'image/jpeg',
      'png' => 'image/png',
      'webp' => 'image/webp',
      _ => null,
    };
  }

  void _showImageError(String message) {
    AppSnackbar.error(context, message);
  }

  Future<List<ChatImageAttachment>> _readImagesFromDevice() async {
    final files = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['jpg', 'jpeg', 'png', 'webp'],
    );
    if (!mounted || files.isEmpty) return const [];

    final selected = <ChatImageAttachment>[];
    for (final file in files) {
      final mimeType = _mimeTypeFor(file.name);
      if (mimeType == null) {
        _showImageError('Không đọc được ảnh ${file.name}.');
        continue;
      }
      late final Uint8List bytes;
      try {
        bytes = await file.readAsBytes();
      } catch (_) {
        if (!mounted) return const [];
        _showImageError('Không đọc được ảnh ${file.name}.');
        continue;
      }
      if (!mounted) return const [];
      if (bytes.length > _maxImageBytes) {
        _showImageError('Ảnh ${file.name} vượt quá giới hạn 4 MB.');
        continue;
      }
      selected.add(
        ChatImageAttachment(bytes: bytes, name: file.name, mimeType: mimeType),
      );
    }
    return selected;
  }

  Future<void> _pickImages() async {
    if (widget.isLoading || _images.length >= _maxImages) return;
    final selected = widget.pickImages == null
        ? await _readImagesFromDevice()
        : await widget.pickImages!();
    if (!mounted || selected.isEmpty) return;

    final slots = _maxImages - _images.length;
    final accepted = <ChatImageAttachment>[];
    for (final image in selected) {
      if (!const {
        'image/jpeg',
        'image/png',
        'image/webp',
      }.contains(image.mimeType.toLowerCase())) {
        _showImageError('Chỉ hỗ trợ ảnh JPG, PNG hoặc WEBP.');
        continue;
      }
      if (image.bytes.length > _maxImageBytes) {
        _showImageError('Ảnh ${image.name} vượt quá giới hạn 4 MB.');
        continue;
      }
      final duplicate = [..._images, ...accepted].any(
        (current) =>
            current.name.toLowerCase() == image.name.toLowerCase() &&
            current.bytes.length == image.bytes.length,
      );
      if (duplicate) {
        _showImageError('Ảnh ${image.name} đã được chọn rồi.');
        continue;
      }
      accepted.add(image);
    }
    if (accepted.length > slots) {
      _showImageError('Mỗi lượt chat chỉ hỗ trợ tối đa 2 ảnh.');
    }
    setState(() => _images.addAll(accepted.take(slots)));
  }

  void _handleSend() {
    final enteredText = _controller.text.trim();
    if ((enteredText.isEmpty && _images.isEmpty) || widget.isLoading) return;
    final text = enteredText.isEmpty
        ? 'Hãy kiểm tra ảnh cây trồng này.'
        : enteredText;
    widget.onSend(text, _deepResearch, List.unmodifiable(_images));
    _controller.clear();
    setState(_images.clear);
    _focusNode.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final canCancel = widget.isLoading && widget.onCancel != null;
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.md,
          10,
          AppSpacing.md,
          AppSpacing.md,
        ),
        decoration: const BoxDecoration(
          color: AppColors.background,
          border: Border(top: BorderSide(color: AppColors.line)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_images.isNotEmpty) ...[
              SizedBox(
                height: 72,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: _images.length,
                  separatorBuilder: (_, _) =>
                      const SizedBox(width: AppSpacing.xs),
                  itemBuilder: (context, index) {
                    final image = _images[index];
                    final sizeKb = (image.bytes.length / 1024).ceil();
                    return Container(
                      width: 220,
                      padding: const EdgeInsets.all(AppSpacing.xs),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(AppRadius.small),
                        border: Border.all(color: AppColors.line),
                      ),
                      child: Row(
                        children: [
                          ClipRRect(
                            borderRadius: BorderRadius.circular(
                              AppRadius.small,
                            ),
                            child: Image.memory(
                              image.bytes,
                              width: 54,
                              height: 54,
                              fit: BoxFit.cover,
                              semanticLabel: 'Ảnh đính kèm ${image.name}',
                            ),
                          ),
                          const SizedBox(width: AppSpacing.xs),
                          Expanded(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  image.name,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  '$sizeKb KB',
                                  style: const TextStyle(
                                    fontSize: 11,
                                    color: AppColors.muted,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            tooltip: 'Bỏ ảnh ${image.name}',
                            onPressed: widget.isLoading
                                ? null
                                : () => setState(() => _images.removeAt(index)),
                            icon: const Icon(Icons.close_rounded, size: 19),
                            color: AppColors.danger,
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 9),
            ],
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                IconButton(
                  tooltip: 'Đính kèm ảnh cây trồng',
                  onPressed: widget.isLoading || _images.length >= _maxImages
                      ? null
                      : _pickImages,
                  icon: const Icon(
                    Icons.add_photo_alternate_outlined,
                    color: AppColors.forest,
                  ),
                ),
                if (_deepResearchAvailable)
                  IconButton(
                    tooltip: _deepResearch
                        ? 'Tắt Deep Research'
                        : 'Bật Deep Research',
                    onPressed: widget.isLoading
                        ? null
                        : () => setState(() => _deepResearch = !_deepResearch),
                    icon: Icon(
                      Icons.travel_explore_rounded,
                      color: _deepResearch ? AppColors.forest : AppColors.muted,
                    ),
                  ),
                Expanded(
                  child: TextField(
                    controller: _controller,
                    focusNode: _focusNode,
                    minLines: 1,
                    maxLines: 4,
                    textCapitalization: TextCapitalization.sentences,
                    onSubmitted: (_) => _handleSend(),
                    onChanged: (_) => setState(() {}),
                    // Keep the field enabled on Flutter Web. Toggling
                    // TextField.enabled around an SSE request can leave the
                    // browser text input connection unusable after the first
                    // message. Sending is still guarded in _handleSend.
                    enabled: true,
                    onTap: () =>
                        FocusScope.of(context).requestFocus(_focusNode),
                    decoration: const InputDecoration(
                      hintText: 'Hỏi hoặc gửi ảnh cây trồng…',
                      prefixIcon: Icon(
                        Icons.eco_outlined,
                        color: AppColors.forest,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Tooltip(
                  message: canCancel
                      ? 'Dừng trả lời'
                      : _canSend
                      ? 'Gửi câu hỏi'
                      : widget.isLoading
                      ? 'AgriMind đang trả lời'
                      : 'Nhập câu hỏi hoặc chọn ảnh',
                  child: Material(
                    color: canCancel
                        ? AppColors.danger
                        : _canSend
                        ? AppColors.forest
                        : AppColors.line,
                    borderRadius: BorderRadius.circular(AppRadius.input),
                    child: InkWell(
                      key: canCancel
                          ? const Key('cancel-chat-response')
                          : const Key('send-chat-message'),
                      onTap: canCancel
                          ? widget.onCancel
                          : (_canSend ? _handleSend : null),
                      borderRadius: BorderRadius.circular(AppRadius.input),
                      child: SizedBox(
                        width: 54,
                        height: 54,
                        child: Icon(
                          canCancel
                              ? Icons.stop_rounded
                              : Icons.arrow_upward_rounded,
                          color: canCancel || _canSend
                              ? AppColors.onPrimary
                              : AppColors.muted,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
