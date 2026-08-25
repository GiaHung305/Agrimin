import 'dart:async';

import 'package:flutter/material.dart';

import 'package:frontend_flutter/data/services/api_service.dart';
import 'package:frontend_flutter/design_system/design_system.dart';
import 'package:frontend_flutter/features/assistant/presentation/chat_screen.dart';
import 'package:frontend_flutter/features/farm/presentation/farm_profile_screen.dart';
import 'package:frontend_flutter/features/notifications/presentation/notifications_screen.dart';
import 'package:frontend_flutter/features/tasks/presentation/tasks_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({
    super.key,
    this.canManageDocuments = false,
    this.canViewOperations = false,
  });

  final bool canManageDocuments;
  final bool canViewOperations;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> with WidgetsBindingObserver {
  int _selectedIndex = 0;
  int _tasksRefreshToken = 0;
  int _notificationsRefreshToken = 0;
  bool _hasOpenTasks = false;
  bool _hasUnreadNotifications = false;
  bool _unreadCountInitialized = false;
  int _lastUnreadCount = 0;
  Timer? _badgePoller;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _refreshNavigationBadges();
    _badgePoller = Timer.periodic(
      const Duration(seconds: 10),
      (_) => _refreshNavigationBadges(),
    );
  }

  @override
  void dispose() {
    _badgePoller?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _refreshNavigationBadges();
    }
  }

  void _refreshNavigationBadges() {
    unawaited(_refreshOpenTasks());
    unawaited(_refreshUnreadNotifications());
  }

  Future<void> _refreshOpenTasks() async {
    try {
      final openTaskCount = await ApiService.getOpenTaskCount();
      if (!mounted) return;
      final hasOpenTasks = openTaskCount > 0;
      if (_hasOpenTasks != hasOpenTasks) {
        setState(() => _hasOpenTasks = hasOpenTasks);
      }
    } catch (_) {
      // Keep the last known badge state during a temporary network failure.
    }
  }

  Future<void> _refreshUnreadNotifications() async {
    try {
      final unreadCount = await ApiService.getUnreadNotificationCount();
      final hasUnread = unreadCount > 0;
      if (!mounted) return;
      final shouldAnnounce =
          _unreadCountInitialized && unreadCount > _lastUnreadCount;
      setState(() {
        _hasUnreadNotifications = hasUnread;
        _unreadCountInitialized = true;
        _lastUnreadCount = unreadCount;
        if (hasUnread && _selectedIndex == 2) {
          _notificationsRefreshToken++;
        }
      });
      if (shouldAnnounce && _selectedIndex != 2) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(
            SnackBar(
              content: Text(
                unreadCount == 1
                    ? 'Bạn có một lời nhắc mới.'
                    : 'Bạn có $unreadCount thông báo chưa đọc.',
              ),
              action: SnackBarAction(
                label: 'Xem',
                onPressed: () => _selectDestination(2),
              ),
            ),
          );
      }
    } catch (_) {
      // Keep the last known badge state during a temporary network failure.
    }
  }

  void _onUnreadChanged(bool hasUnread) {
    if (!mounted) return;
    setState(() {
      _hasUnreadNotifications = hasUnread;
      if (!hasUnread) _lastUnreadCount = 0;
    });
  }

  void _markTasksChanged() {
    if (!mounted) return;
    setState(() => _tasksRefreshToken++);
    unawaited(_refreshOpenTasks());
  }

  void _onTasksScreenChanged() {
    unawaited(_refreshOpenTasks());
  }

  void _selectDestination(int index) {
    setState(() {
      _selectedIndex = index;
      if (index == 1) _tasksRefreshToken++;
      if (index == 2) _notificationsRefreshToken++;
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: IndexedStack(
      index: _selectedIndex,
      children: [
        ChatScreen(
          canManageDocuments: widget.canManageDocuments,
          canViewOperations: widget.canViewOperations,
          onTaskChanged: _markTasksChanged,
          hasUnreadNotifications: _hasUnreadNotifications,
          onNotificationsTap: () => _selectDestination(2),
        ),
        TasksScreen(
          refreshToken: _tasksRefreshToken,
          onTaskChanged: _onTasksScreenChanged,
        ),
        NotificationsScreen(
          isActive: _selectedIndex == 2,
          refreshToken: _notificationsRefreshToken,
          onTaskChanged: _markTasksChanged,
          onUnreadChanged: _onUnreadChanged,
        ),
        const FarmProfileScreen(),
      ],
    ),
    bottomNavigationBar: SafeArea(
      top: false,
      child: Container(
        decoration: const BoxDecoration(
          color: AppColors.surface,
          border: Border(top: BorderSide(color: AppColors.line)),
        ),
        child: NavigationBar(
          height: 69,
          backgroundColor: AppColors.surface,
          indicatorColor: AppColors.mint,
          selectedIndex: _selectedIndex,
          onDestinationSelected: _selectDestination,
          destinations: [
            const NavigationDestination(
              icon: Icon(Icons.forum_outlined),
              selectedIcon: Icon(Icons.forum_rounded),
              label: 'Trợ lý',
            ),
            NavigationDestination(
              icon: StatusBadgeIcon(
                icon: Icons.checklist_outlined,
                selectedIcon: Icons.checklist_rounded,
                showBadge: _hasOpenTasks,
                activeSemanticsLabel: 'Có công việc đang làm',
                inactiveSemanticsLabel: 'Không có công việc đang làm',
                badgeKey: const Key('open-task-badge'),
              ),
              selectedIcon: StatusBadgeIcon(
                icon: Icons.checklist_outlined,
                selectedIcon: Icons.checklist_rounded,
                showBadge: _hasOpenTasks,
                selected: true,
                activeSemanticsLabel: 'Có công việc đang làm',
                inactiveSemanticsLabel: 'Không có công việc đang làm',
                badgeKey: const Key('selected-open-task-badge'),
              ),
              label: 'Công việc',
            ),
            NavigationDestination(
              icon: StatusBadgeIcon(
                icon: Icons.notifications_none_rounded,
                selectedIcon: Icons.notifications_rounded,
                showBadge: _hasUnreadNotifications,
                activeSemanticsLabel: 'Có thông báo mới chưa đọc',
                inactiveSemanticsLabel: 'Không có thông báo mới',
                badgeKey: const Key('unread-notification-badge'),
              ),
              selectedIcon: StatusBadgeIcon(
                icon: Icons.notifications_none_rounded,
                selectedIcon: Icons.notifications_rounded,
                showBadge: _hasUnreadNotifications,
                selected: true,
                activeSemanticsLabel: 'Có thông báo mới chưa đọc',
                inactiveSemanticsLabel: 'Không có thông báo mới',
                badgeKey: const Key('selected-unread-notification-badge'),
              ),
              label: 'Thông báo',
            ),
            const NavigationDestination(
              icon: Icon(Icons.agriculture_outlined),
              selectedIcon: Icon(Icons.agriculture_rounded),
              label: 'Nông trại',
            ),
          ],
        ),
      ),
    ),
  );
}
