import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../models/document.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  List<DocumentItem> _documents = [];
  bool _isLoading = true;
  bool _isUploading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadDocuments();
  }

  Future<void> _loadDocuments() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final documents = await ApiService.getDocuments();
      if (!mounted) return;
      setState(() {
        _documents = documents;
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _handleUpload() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf'],
      withData: true,
    );
    if (!mounted || result == null || result.files.single.bytes == null) {
      return;
    }
    final file = result.files.single;
    final metadata = await _requestMetadata(file.name);
    if (!mounted || metadata == null) return;

    setState(() => _isUploading = true);
    try {
      await ApiService.uploadDocument(
        fileBytes: file.bytes!,
        fileName: file.name,
        title: metadata.title,
        source: metadata.source.isEmpty ? null : metadata.source,
        version: metadata.version.isEmpty ? null : metadata.version,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Đã tải tài liệu lên và đưa vào kho kiến thức.'),
        ),
      );
      await _loadDocuments();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Không thể tải tài liệu: $error')),
        );
      }
    } finally {
      if (mounted) setState(() => _isUploading = false);
    }
  }

  Future<_DocumentMetadata?> _requestMetadata(String filename) {
    final title = TextEditingController(
      text: filename.replaceFirst(RegExp(r'\.pdf$', caseSensitive: false), ''),
    );
    final source = TextEditingController();
    final version = TextEditingController(text: 'v1');
    return showDialog<_DocumentMetadata>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Thêm tài liệu PDF'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: title,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Tiêu đề *'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: source,
                decoration: const InputDecoration(
                  labelText: 'Nguồn (không bắt buộc)',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: version,
                decoration: const InputDecoration(labelText: 'Phiên bản'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(
              dialogContext,
              _DocumentMetadata(
                title.text.trim(),
                source.text.trim(),
                version.text.trim(),
              ),
            ),
            child: const Text('Tải lên'),
          ),
        ],
      ),
    ).whenComplete(() {
      title.dispose();
      source.dispose();
      version.dispose();
    });
  }

  Future<void> _handleDeactivate(DocumentItem document) async {
    final accepted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Ngừng dùng tài liệu?'),
        content: Text(
          '“${document.title}” sẽ không còn được dùng để trả lời các câu hỏi mới.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Giữ lại'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Ngừng dùng'),
          ),
        ],
      ),
    );
    if (accepted != true) {
      return;
    }
    try {
      await ApiService.deactivateDocument(document.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã ngừng dùng tài liệu này.')),
      );
      await _loadDocuments();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Không thể cập nhật tài liệu: $error')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final activeCount = _documents
        .where((document) => document.isActive)
        .length;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Kho kiến thức'),
        actions: [
          IconButton(
            onPressed: _isLoading ? null : _loadDocuments,
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Làm mới',
          ),
          const SizedBox(width: 6),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _isUploading ? null : _handleUpload,
        backgroundColor: AppColors.forest,
        foregroundColor: Colors.white,
        icon: _isUploading
            ? const SizedBox(
                width: 19,
                height: 19,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white,
                ),
              )
            : const Icon(Icons.upload_file_rounded),
        label: Text(_isUploading ? 'Đang tải…' : 'Thêm PDF'),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
          ? _LoadError(message: _error!, onRetry: _loadDocuments)
          : RefreshIndicator(
              onRefresh: _loadDocuments,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 100),
                children: [
                  _KnowledgeHero(total: _documents.length, active: activeCount),
                  const SizedBox(height: 24),
                  Text(
                    'Tài liệu đã nạp',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 5),
                  const Text(
                    'Tài liệu đang bật sẽ được trợ lý ưu tiên tham khảo.',
                    style: TextStyle(color: AppColors.muted, fontSize: 13),
                  ),
                  const SizedBox(height: 14),
                  if (_documents.isEmpty)
                    const _EmptyDocuments()
                  else
                    ..._documents.map(
                      (document) => Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: _DocumentCard(
                          document: document,
                          onDeactivate: () => _handleDeactivate(document),
                        ),
                      ),
                    ),
                ],
              ),
            ),
    );
  }
}

class _DocumentMetadata {
  const _DocumentMetadata(this.title, this.source, this.version);
  final String title;
  final String source;
  final String version;
}

class _KnowledgeHero extends StatelessWidget {
  const _KnowledgeHero({required this.total, required this.active});
  final int total;
  final int active;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: const LinearGradient(
          colors: [AppColors.forestDark, AppColors.forest],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 52,
            height: 52,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: .16),
              borderRadius: BorderRadius.circular(16),
            ),
            child: const Icon(
              Icons.auto_stories_rounded,
              color: AppColors.lime,
              size: 28,
            ),
          ),
          const SizedBox(width: 15),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Nguồn tri thức cho AgriMind',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  '$active đang sử dụng • $total tài liệu',
                  style: const TextStyle(
                    color: Color(0xFFD3EBDD),
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DocumentCard extends StatelessWidget {
  const _DocumentCard({required this.document, required this.onDeactivate});
  final DocumentItem document;
  final VoidCallback onDeactivate;

  @override
  Widget build(BuildContext context) {
    final date = document.ingestedAt.isEmpty
        ? 'Chưa rõ ngày nạp'
        : document.ingestedAt.split('T').first;
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(15, 15, 12, 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: document.isActive
                    ? AppColors.mint
                    : const Color(0xFFF0F2F1),
                borderRadius: BorderRadius.circular(13),
              ),
              child: Icon(
                Icons.picture_as_pdf_outlined,
                color: document.isActive ? AppColors.forest : AppColors.muted,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    document.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      color: AppColors.ink,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    '${document.source ?? 'Không rõ nguồn'} • ${document.version ?? 'Không rõ phiên bản'}',
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 7),
                  Row(
                    children: [
                      Icon(
                        Icons.schedule_rounded,
                        size: 14,
                        color: AppColors.muted,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        date,
                        style: const TextStyle(
                          color: AppColors.muted,
                          fontSize: 12,
                        ),
                      ),
                      const Spacer(),
                      _StatusPill(active: document.isActive),
                    ],
                  ),
                ],
              ),
            ),
            if (document.isActive)
              PopupMenuButton<String>(
                tooltip: 'Tùy chọn',
                onSelected: (_) => onDeactivate(),
                itemBuilder: (_) => const [
                  PopupMenuItem(value: 'deactivate', child: Text('Ngừng dùng')),
                ],
                icon: const Icon(
                  Icons.more_horiz_rounded,
                  color: AppColors.muted,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.active});
  final bool active;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: active ? AppColors.mint : const Color(0xFFF0F2F1),
      borderRadius: BorderRadius.circular(99),
    ),
    child: Text(
      active ? 'Đang dùng' : 'Đã tắt',
      style: TextStyle(
        color: active ? AppColors.forest : AppColors.muted,
        fontSize: 11,
        fontWeight: FontWeight.w700,
      ),
    ),
  );
}

class _EmptyDocuments extends StatelessWidget {
  const _EmptyDocuments();
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(28),
    decoration: BoxDecoration(
      color: Colors.white,
      border: Border.all(color: AppColors.line),
      borderRadius: BorderRadius.circular(22),
    ),
    child: const Column(
      children: [
        Icon(Icons.folder_open_outlined, size: 42, color: AppColors.muted),
        SizedBox(height: 12),
        Text(
          'Kho kiến thức đang trống',
          style: TextStyle(fontWeight: FontWeight.w700, color: AppColors.ink),
        ),
        SizedBox(height: 5),
        Text(
          'Tải lên tài liệu PDF để AgriMind có thêm nguồn tham khảo.',
          textAlign: TextAlign.center,
          style: TextStyle(color: AppColors.muted, fontSize: 13, height: 1.4),
        ),
      ],
    ),
  );
}

class _LoadError extends StatelessWidget {
  const _LoadError({required this.message, required this.onRetry});
  final String message;
  final Future<void> Function() onRetry;
  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(
            Icons.cloud_off_outlined,
            size: 46,
            color: AppColors.muted,
          ),
          const SizedBox(height: 14),
          const Text(
            'Không tải được kho tài liệu',
            style: TextStyle(fontWeight: FontWeight.w800, color: AppColors.ink),
          ),
          const SizedBox(height: 7),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: AppColors.muted, fontSize: 12),
          ),
          const SizedBox(height: 16),
          OutlinedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Thử lại'),
          ),
        ],
      ),
    ),
  );
}
