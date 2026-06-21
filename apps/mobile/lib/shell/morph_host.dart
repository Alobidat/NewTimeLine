/// Drives the "flying media" morph: when an event is picked from a map pin or a summary
/// montage tile, its image lifts off from where it was tapped and glides into the detail
/// panel's header slot — so the detail literally *emerges from the map* rather than just
/// swapping in. Any descendant can trigger it via [MorphScope.maybeOf]; the panel registers
/// the landing region with [targetKey]. Entirely defensive: if rects aren't available it
/// just no-ops and the normal cross-fade still happens.
library;

import 'package:flutter/material.dart';

class MorphHost extends StatefulWidget {
  const MorphHost({super.key, required this.child});
  final Widget child;

  @override
  State<MorphHost> createState() => MorphHostState();
}

class MorphHostState extends State<MorphHost> with SingleTickerProviderStateMixin {
  /// The panel attaches this to the region a flown image should land on.
  final GlobalKey targetKey = GlobalKey();

  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 480),
  )..addStatusListener((s) {
      if (s == AnimationStatus.completed || s == AnimationStatus.dismissed) {
        _remove();
      }
    });

  OverlayEntry? _entry;
  Rect _from = Rect.zero;
  Rect _to = Rect.zero;
  String? _url;

  /// Launch a flight of [imageUrl] from [source]'s box into the registered target.
  void fly(BuildContext source, String imageUrl) {
    final src = source.findRenderObject();
    final dst = targetKey.currentContext?.findRenderObject();
    final overlay = Overlay.maybeOf(context);
    if (src is! RenderBox || dst is! RenderBox || overlay == null) return;
    if (!src.hasSize || !dst.hasSize) return;
    _from = src.localToGlobal(Offset.zero) & src.size;
    _to = dst.localToGlobal(Offset.zero) & dst.size;
    _url = imageUrl;
    _remove();
    _entry = OverlayEntry(builder: _buildFlight);
    overlay.insert(_entry!);
    _c.forward(from: 0);
  }

  void _remove() {
    _entry?.remove();
    _entry = null;
  }

  Widget _buildFlight(BuildContext _) => AnimatedBuilder(
    animation: _c,
    builder: (_, _) {
      final t = Curves.easeInOutCubic.transform(_c.value);
      final rect = Rect.lerp(_from, _to, t)!;
      // Hold opaque most of the way, then fade out as the panel content takes over.
      final fade = t < 0.8 ? 1.0 : (1 - (t - 0.8) / 0.2);
      return Positioned.fromRect(
        rect: rect,
        child: IgnorePointer(
          child: Opacity(
            opacity: fade.clamp(0.0, 1.0),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.network(
                _url!,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => const SizedBox.shrink(),
              ),
            ),
          ),
        ),
      );
    },
  );

  @override
  void dispose() {
    _remove();
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      MorphScope(state: this, child: widget.child);
}

class MorphScope extends InheritedWidget {
  const MorphScope({super.key, required this.state, required super.child});
  final MorphHostState state;

  GlobalKey get targetKey => state.targetKey;
  void fly(BuildContext source, String imageUrl) => state.fly(source, imageUrl);

  static MorphScope? maybeOf(BuildContext c) =>
      c.dependOnInheritedWidgetOfExactType<MorphScope>();

  @override
  bool updateShouldNotify(MorphScope old) => false;
}
