import 'package:flutter/animation.dart';

/// Motion tokens keep state changes predictable and accessible.
abstract final class AppMotion {
  static const fast = Duration(milliseconds: 140);
  static const standard = Duration(milliseconds: 220);
  static const emphasized = Duration(milliseconds: 320);
  static const curve = Curves.easeOutCubic;
}
