import 'package:flutter/material.dart';

class StatusBadgeIcon extends StatelessWidget {
  const StatusBadgeIcon({
    super.key,
    required this.icon,
    required this.selectedIcon,
    required this.showBadge,
    required this.activeSemanticsLabel,
    required this.inactiveSemanticsLabel,
    required this.badgeKey,
    this.selected = false,
  });

  final IconData icon;
  final IconData selectedIcon;
  final bool showBadge;
  final bool selected;
  final String activeSemanticsLabel;
  final String inactiveSemanticsLabel;
  final Key badgeKey;

  @override
  Widget build(BuildContext context) => Semantics(
    label: showBadge ? activeSemanticsLabel : inactiveSemanticsLabel,
    child: Stack(
      clipBehavior: Clip.none,
      children: [
        Icon(selected ? selectedIcon : icon),
        if (showBadge)
          Positioned(
            top: -1,
            right: -2,
            child: Container(
              key: badgeKey,
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.error,
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 1.25),
              ),
            ),
          ),
      ],
    ),
  );
}
