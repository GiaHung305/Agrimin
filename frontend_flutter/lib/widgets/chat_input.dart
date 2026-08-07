import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../models/chat_image.dart';
import '../theme/app_theme.dart';

class ChatInput extends StatefulWidget {
  final void Function(
    String text,
    bool deepResearch,
    List<ChatImageAttachment> images,
  )
  onSend;
  final bool isLoading;

  const ChatInput({super.key, required this.onSend, required this.isLoading});

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
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _pickImages() async {
    if (widget.isLoading || _images.length >= _maxImages) return;
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['jpg', 'jpeg', 'png', 'webp'],
      allowMultiple: true,
      withData: true,
    );
    if (!mounted || result == null) return;

    final selected = <ChatImageAttachment>[];
    for (final file in result.files) {
      final bytes = file.bytes;
      final mimeType = _mimeTypeFor(file.name);
      if (bytes == null || mimeType == null) {
        _showImageError('Không đọc được ảnh ${file.name}.');
        continue;
      }
      if (bytes.length > _maxImageBytes) {
        _showImageError('Ảnh ${file.name} vượt quá giới hạn 4 MB.');
        continue;
      }
      selected.add(
        ChatImageAttachment(bytes: bytes, name: file.name, mimeType: mimeType),
      );
    }
    final slots = _maxImages - _images.length;
    if (selected.length > slots) {
      _showImageError('Mỗi lượt chat chỉ hỗ trợ tối đa 2 ảnh.');
    }
    setState(() => _images.addAll(selected.take(slots)));
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
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 16),
        decoration: const BoxDecoration(
          color: AppColors.background,
          border: Border(top: BorderSide(color: AppColors.line)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_images.isNotEmpty) ...[
              SizedBox(
                height: 66,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: _images.length,
                  separatorBuilder: (_, _) => const SizedBox(width: 8),
                  itemBuilder: (context, index) => Stack(
                    clipBehavior: Clip.none,
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(12),
                        child: Image.memory(
                          _images[index].bytes,
                          width: 66,
                          height: 66,
                          fit: BoxFit.cover,
                        ),
                      ),
                      Positioned(
                        right: -6,
                        top: -6,
                        child: InkWell(
                          onTap: widget.isLoading
                              ? null
                              : () => setState(() => _images.removeAt(index)),
                          child: const CircleAvatar(
                            radius: 10,
                            backgroundColor: AppColors.ink,
                            child: Icon(
                              Icons.close,
                              size: 13,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
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
                    enabled: !widget.isLoading,
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
                Material(
                  color: widget.isLoading ? AppColors.line : AppColors.forest,
                  borderRadius: BorderRadius.circular(18),
                  child: InkWell(
                    onTap: widget.isLoading ? null : _handleSend,
                    borderRadius: BorderRadius.circular(18),
                    child: SizedBox(
                      width: 54,
                      height: 54,
                      child: Icon(
                        widget.isLoading
                            ? Icons.more_horiz
                            : Icons.arrow_upward_rounded,
                        color: widget.isLoading
                            ? AppColors.muted
                            : Colors.white,
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
