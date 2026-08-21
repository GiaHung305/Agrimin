import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'package:frontend_flutter/app/agrimind_app.dart';
import 'package:frontend_flutter/data/services/push_notification_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Push notifications currently use the Android Firebase setup. Keep them
  // out of the Web startup path so Chrome can run the Supabase/API UI without
  // requiring Firebase Web configuration.
  if (!kIsWeb) {
    await Firebase.initializeApp();
    FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
    await PushNotificationService.initialize();
  }
  runApp(const AgriMindApp());
}
