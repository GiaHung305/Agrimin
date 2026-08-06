import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'api_service.dart';

const _notificationChannel = AndroidNotificationChannel(
  'agrimind_reminders',
  'Nhắc việc AgriMind',
  description: 'Nhắc việc nông trại và cảnh báo thời tiết',
  importance: Importance.high,
);

final _localNotifications = FlutterLocalNotificationsPlugin();

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // Notification payloads are rendered by Android in the background. This
  // handler is intentionally lightweight so the OS does not terminate it.
}

class PushNotificationService {
  static StreamSubscription<String>? _tokenRefreshSubscription;
  static StreamSubscription<RemoteMessage>? _foregroundSubscription;

  static Future<void> initialize() async {
    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    await _localNotifications.initialize(settings: const InitializationSettings(android: androidSettings));
    await _localNotifications
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(_notificationChannel);

    await FirebaseMessaging.instance.requestPermission(alert: true, badge: true, sound: true);
    _foregroundSubscription ??= FirebaseMessaging.onMessage.listen(_showForegroundNotification);
  }

  static Future<void> registerCurrentDevice() async {
    final token = await FirebaseMessaging.instance.getToken();
    if (token != null) await ApiService.registerDeviceToken(token);
    _tokenRefreshSubscription ??= FirebaseMessaging.instance.onTokenRefresh.listen((newToken) {
      ApiService.registerDeviceToken(newToken).catchError((_) {});
    });
  }

  static Future<void> _showForegroundNotification(RemoteMessage message) async {
    final notification = message.notification;
    if (notification == null) return;
    await _localNotifications.show(
      id: notification.hashCode,
      title: notification.title,
      body: notification.body,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          'agrimind_reminders',
          'Nhắc việc AgriMind',
          channelDescription: 'Nhắc việc nông trại và cảnh báo thời tiết',
          importance: Importance.high,
          priority: Priority.high,
        ),
      ),
    );
  }
}
