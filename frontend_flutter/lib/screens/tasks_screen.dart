import 'package:flutter/material.dart';

import '../models/farm_task.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key});

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  late Future<List<FarmTask>> _tasks;

  @override
  void initState() {
    super.initState();
    _tasks = ApiService.getTasks();
  }

  Future<void> _reload() async => setState(() => _tasks = ApiService.getTasks());

  Future<void> _delete(FarmTask task) async {
    final approved = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Xóa công việc?'),
        content: Text('“${task.title}” sẽ được xóa khỏi danh sách.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Giữ lại')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Xóa')),
        ],
      ),
    );
    if (approved != true) return;
    await ApiService.deleteTask(task.id);
    await _reload();
  }

  Future<void> _toggleCompleted(FarmTask task, bool completed) async {
    await ApiService.updateTask(task.id, {'status': completed ? 'completed' : 'open'});
    await _reload();
  }

  Future<void> _edit(FarmTask task) async {
    final controller = TextEditingController(text: task.title);
    final title = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sửa công việc'),
        content: TextField(controller: controller, autofocus: true, maxLength: 255, decoration: const InputDecoration(labelText: 'Tên công việc')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Hủy')),
          FilledButton(onPressed: () => Navigator.pop(context, controller.text.trim()), child: const Text('Lưu')),
        ],
      ),
    );
    if (title == null || title.isEmpty || title == task.title) return;
    await ApiService.updateTask(task.id, {'title': title});
    await _reload();
  }

  String _dueLabel(FarmTask task) {
    if (task.dueAt == null) return 'Chưa lên lịch nhắc';
    final due = task.dueAt!;
    return '${due.hour.toString().padLeft(2, '0')}:${due.minute.toString().padLeft(2, '0')} · ${due.day}/${due.month}/${due.year}';
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Công việc nông trại', style: TextStyle(fontWeight: FontWeight.w800))),
        body: FutureBuilder<List<FarmTask>>(
          future: _tasks,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
            if (snapshot.hasError) return Center(child: Text('Không tải được công việc: ${snapshot.error}'));
            final tasks = snapshot.data ?? [];
            final open = tasks.where((task) => task.status == 'open').toList();
            final done = tasks.where((task) => task.status == 'completed').toList();
            return RefreshIndicator(
              color: AppColors.forest,
              onRefresh: _reload,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
                children: [
                  _TaskSummary(openCount: open.length, doneCount: done.length),
                  const SizedBox(height: 22),
                  if (tasks.isEmpty)
                    const _EmptyTasks()
                  else ...[
                    _SectionTitle(title: 'Cần làm', count: open.length),
                    const SizedBox(height: 9),
                    ...open.map((task) => _TaskTile(task: task, dueLabel: _dueLabel(task), onToggle: _toggleCompleted, onEdit: _edit, onDelete: _delete)),
                    if (done.isNotEmpty) ...[
                      const SizedBox(height: 18),
                      _SectionTitle(title: 'Đã hoàn thành', count: done.length),
                      const SizedBox(height: 9),
                      ...done.map((task) => _TaskTile(task: task, dueLabel: _dueLabel(task), onToggle: _toggleCompleted, onEdit: _edit, onDelete: _delete)),
                    ],
                  ],
                ],
              ),
            );
          },
        ),
      );
}

class _TaskSummary extends StatelessWidget {
  final int openCount;
  final int doneCount;
  const _TaskSummary({required this.openCount, required this.doneCount});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(19),
        decoration: BoxDecoration(
          color: AppColors.forest,
          borderRadius: BorderRadius.circular(23),
        ),
        child: Row(children: [
          const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Nhịp làm việc hôm nay', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 17)),
            SizedBox(height: 5),
            Text('Theo dõi việc cần làm để không bỏ lỡ lịch chăm sóc.', style: TextStyle(color: Color(0xFFD8F1E2), fontSize: 12, height: 1.35)),
          ])),
          const SizedBox(width: 15),
          Column(children: [
            _Count(value: openCount, label: 'cần làm'),
            const SizedBox(height: 8),
            _Count(value: doneCount, label: 'đã xong'),
          ]),
        ]),
      );
}

class _Count extends StatelessWidget {
  final int value;
  final String label;
  const _Count({required this.value, required this.label});
  @override
  Widget build(BuildContext context) => Row(children: [
        Text('$value', style: const TextStyle(color: AppColors.lime, fontSize: 19, fontWeight: FontWeight.w800)),
        const SizedBox(width: 5),
        Text(label, style: const TextStyle(color: Colors.white, fontSize: 11)),
      ]);
}

class _SectionTitle extends StatelessWidget {
  final String title;
  final int count;
  const _SectionTitle({required this.title, required this.count});
  @override
  Widget build(BuildContext context) => Row(children: [
        Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: AppColors.ink)),
        const SizedBox(width: 7),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(color: AppColors.mint, borderRadius: BorderRadius.circular(10)),
          child: Text('$count', style: const TextStyle(color: AppColors.forest, fontSize: 12, fontWeight: FontWeight.w700)),
        ),
      ]);
}

class _TaskTile extends StatelessWidget {
  final FarmTask task;
  final String dueLabel;
  final Future<void> Function(FarmTask task, bool completed) onToggle;
  final Future<void> Function(FarmTask task) onEdit;
  final Future<void> Function(FarmTask task) onDelete;

  const _TaskTile({required this.task, required this.dueLabel, required this.onToggle, required this.onEdit, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final completed = task.status == 'completed';
    return Card(
      margin: const EdgeInsets.only(bottom: 9),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 9, 8, 9),
        child: Row(children: [
          Checkbox(value: completed, activeColor: AppColors.forest, onChanged: (value) => onToggle(task, value ?? false)),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(task.title, maxLines: 2, overflow: TextOverflow.ellipsis,
                style: TextStyle(fontWeight: FontWeight.w700, color: completed ? AppColors.muted : AppColors.ink,
                    decoration: completed ? TextDecoration.lineThrough : null)),
            const SizedBox(height: 5),
            Row(children: [
              Icon(task.dueAt == null ? Icons.schedule_outlined : Icons.notifications_active_outlined, size: 14, color: AppColors.muted),
              const SizedBox(width: 5),
              Expanded(child: Text(dueLabel, style: const TextStyle(fontSize: 12, color: AppColors.muted), overflow: TextOverflow.ellipsis)),
            ]),
          ])),
          PopupMenuButton<String>(
            onSelected: (value) => value == 'edit' ? onEdit(task) : onDelete(task),
            itemBuilder: (context) => const [
              PopupMenuItem(value: 'edit', child: Text('Sửa tên')),
              PopupMenuItem(value: 'delete', child: Text('Xóa')),
            ],
            icon: const Icon(Icons.more_vert_rounded, color: AppColors.muted),
          ),
        ]),
      ),
    );
  }
}

class _EmptyTasks extends StatelessWidget {
  const _EmptyTasks();
  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.only(top: 44),
        child: Column(children: [
          Icon(Icons.task_alt_rounded, size: 56, color: AppColors.lime),
          SizedBox(height: 13),
          Text('Chưa có công việc nào', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          SizedBox(height: 6),
          Text('Hãy nhắn trợ lý để tạo nhắc việc đầu tiên.', textAlign: TextAlign.center, style: TextStyle(color: AppColors.muted)),
        ]),
      );
}
