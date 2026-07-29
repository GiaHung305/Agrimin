import 'package:flutter/material.dart';
import '../models/document.dart';
import '../services/api_service.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  List<DocumentItem> _documents = [];
  bool _isLoading = true;
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