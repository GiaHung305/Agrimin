import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

class ChatInput extends StatefulWidget {
  final ValueChanged<String> onSend;
  final bool isLoading;

  const ChatInput({super.key, required this.onSend, required this.isLoading});

  @override
  State<ChatInput> createState() => _ChatInputState();
}

class _ChatInputState extends State<ChatInput> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _handleSend() {
    final text = _controller.text.trim();
    if (text.isEmpty || widget.isLoading) return;
    widget.onSend(text);
    _controller.clear();
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
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
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
                  hintText: 'Hỏi về cây trồng, thời tiết hoặc việc cần làm…',
                  prefixIcon: Icon(Icons.eco_outlined, color: AppColors.forest),
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
                  child: Icon(widget.isLoading ? Icons.more_horiz : Icons.arrow_upward_rounded,
                      color: widget.isLoading ? AppColors.muted : Colors.white),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
