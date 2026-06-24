/// A circular user avatar: the profile picture when one exists, else a deterministic
/// **initials** circle (colored from the name) so every user — including email-login users
/// with no photo — has a recognisable icon. Falls back to initials on any image load error.
library;

import 'package:flutter/material.dart';

class Avatar extends StatelessWidget {
  const Avatar({super.key, required this.label, this.url, this.radius = 20});

  /// Name/handle used for the initials + the deterministic background color.
  final String label;

  /// Profile-picture URL, or null/empty to render initials.
  final String? url;
  final double radius;

  static const _palette = <Color>[
    Color(0xFF6C8EBF), Color(0xFF9673A6), Color(0xFFD79B00), Color(0xFF82B366),
    Color(0xFFB85450), Color(0xFF4FA3A5), Color(0xFFC2698D), Color(0xFF7D8CC4),
  ];

  String get _initials {
    final words = label.trim().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
    if (words.isEmpty) return '?';
    final first = words.first.characters.first;
    final second = words.length > 1 ? words[1].characters.first : '';
    return (first + second).toUpperCase();
  }

  Color get _bg {
    final sum = label.codeUnits.fold<int>(0, (a, b) => a + b);
    return _palette[sum % _palette.length];
  }

  /// Absolute photo URL, or null to render initials. OAuth pictures are already absolute;
  /// server-relative avatars (e.g. a bot's `/api/media/{id}/raw`) are resolved against the
  /// page origin so they load.
  String? get _resolvedUrl {
    final u = url;
    if (u == null || u.isEmpty) return null;
    if (u.startsWith('http://') || u.startsWith('https://')) return u;
    if (u.startsWith('/')) {
      final origin = Uri.base.origin;
      if (origin.isNotEmpty && origin != 'null') return '$origin$u';
    }
    return u;
  }

  @override
  Widget build(BuildContext context) {
    final size = radius * 2;
    final fallback = Container(
      width: size,
      height: size,
      color: _bg,
      alignment: Alignment.center,
      child: Text(
        _initials,
        style: TextStyle(
          color: Colors.white,
          fontSize: radius * 0.8,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
    final resolved = _resolvedUrl;
    return ClipOval(
      child: SizedBox(
        width: size,
        height: size,
        child: resolved != null
            ? Image.network(
                resolved,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => fallback,
                loadingBuilder: (ctx, child, p) => p == null ? child : fallback,
              )
            : fallback,
      ),
    );
  }
}
