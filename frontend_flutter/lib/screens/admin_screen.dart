import 'package:flutter/material.dart';
import '../models/document.dart';
import '../services/api_service.dart';
import 'package:file_picker/file_picker.dart';
class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  List<DocumentItem> _documents = [];
  bool _isLoading = true;
  String? _error;
  bool _isUploading = false;

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
      final docs = await ApiService.getDocuments();
      setState(() {
        _documents = docs;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _isLoading = false;
      });
    }
  }

    Future<void> _handleUpload() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ["pdf"],
      withData: true,
    );

    if (result == null || result.files.single.bytes == null) return;

    final file = result.files.single;

    final titleController = TextEditingController(text: file.name.replaceAll(".pdf", ""));
    final sourceController = TextEditingController();
    final versionController = TextEditingController(text: "v1");

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text("Thông tin tài liệu"),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: titleController, decoration: const InputDecoration(labelText: "Tiêu đề")),
            TextField(controller: sourceController, decoration: const InputDecoration(labelText: "Nguồn")),
            TextField(controller: versionController, decoration: const InputDecoration(labelText: "Phiên bản")),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text("Hủy")),
          ElevatedButton(onPressed: () => Navigator.pop(context, true), child: const Text("Upload")),
        ],
      ),
    );

    if (confirmed != true) return;

    setState(() => _isUploading = true);

    try {
      await ApiService.uploadDocument(
        fileBytes: file.bytes!,
        fileName: file.name,
        title: titleController.text,
        source: sourceController.text.isEmpty ? null : sourceController.text,
        version: versionController.text.isEmpty ? null : versionController.text,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Upload thành công")),
        );
      }
      _loadDocuments();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Lỗi upload: $e")),
        );
      }
    } finally {
      setState(() => _isUploading = false);
    }
  }

  Future<void> _handleDeactivate(String documentId) async {
    try {
      await ApiService.deactivateDocument(documentId);
      _loadDocuments(); // reload lại danh sách sau khi deactivate
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Lỗi: $e")),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Quản lý Tài liệu"),
        actions: [
          if (_isUploading)
            const Padding(
              padding: EdgeInsets.all(12),
              child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
            )
          else
            IconButton(
              icon: const Icon(Icons.upload_file),
              tooltip: "Upload PDF",
              onPressed: _handleUpload,
            ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadDocuments,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text("Lỗi: $_error"))
              : ListView.builder(
                  itemCount: _documents.length,
                  itemBuilder: (context, index) {
                    final doc = _documents[index];
                    return Card(
                      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      child: ListTile(
                        title: Text(doc.title),
                        subtitle: Text(
                          "Nguồn: ${doc.source ?? 'N/A'} • Version: ${doc.version ?? 'N/A'}\n"
                          "Ngày nạp: ${doc.ingestedAt.split('T').first}",
                        ),
                        isThreeLine: true,
                        leading: Icon(
                          doc.isActive ? Icons.check_circle : Icons.cancel,
                          color: doc.isActive ? Colors.green : Colors.grey,
                        ),
                        trailing: doc.isActive
                            ? TextButton(
                                onPressed: () => _handleDeactivate(doc.id),
                                child: const Text("Deactivate"),
                              )
                            : const Text(
                                "Đã tắt",
                                style: TextStyle(color: Colors.grey),
                              ),
                      ),
                    );
                  },
                ),
    );
  }
}