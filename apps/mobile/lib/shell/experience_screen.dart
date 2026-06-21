/// The main experience: a search bar on top, the abstract silhouette map of the involved
/// countries, an inline panel that *morphs* between a timeframe summary and a single-event
/// detail, and the timeline as the central level-of-detail control. Everything is linked by
/// one [TimeWindow] + one [SelectionModel]; selecting/clearing or scrubbing time animates the
/// camera and morphs the panel — no modal popups.
library;

import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../domain/time_format.dart';
import '../event/detail_panel.dart';
import '../map/animated_map_controller.dart';
import '../map/country_atlas.dart';
import '../map/silhouette_map.dart';
import '../search/top_search_bar.dart';
import '../state/selection_model.dart';
import '../state/time_window.dart';
import '../summary/summary_model.dart';
import '../summary/summary_panel.dart';
import '../timeline/timeline_controller.dart';
import '../timeline/vertical_timeline.dart';
import 'morph_host.dart';

const _kWideBreakpoint = 900.0;

class ExperienceScreen extends StatefulWidget {
  const ExperienceScreen({super.key});

  @override
  State<ExperienceScreen> createState() => _ExperienceScreenState();
}

class _ExperienceScreenState extends State<ExperienceScreen>
    with SingleTickerProviderStateMixin {
  final TimeWindow _window = TimeWindow();
  late final TimelineController _timeline = TimelineController(window: _window);
  late final SummaryModel _summary =
      SummaryModel(window: _window, api: _timeline.api);
  final SelectionModel _selection = SelectionModel();
  late final AnimatedMapController _cam = AnimatedMapController(vsync: this);

  ApiClient get _api => _timeline.api;

  CountryAtlas _atlas = CountryAtlas(const []);
  bool _mapReady = false;

  // Detail-mode state (the currently focused event, loaded once at screen level).
  EventDetail? _detail;
  bool _loadingDetail = false;
  String? _detailError;

  bool _panelOnRight = true;

  @override
  void initState() {
    super.initState();
    CountryAtlas.load().then((a) {
      if (!mounted) return;
      setState(() => _atlas = a);
      if (_mapReady && _selection.mode == ViewMode.summary) _fitSummary();
    });
    _selection.addListener(_onChange);
    _summary.addListener(_onSummary);
    _timeline.reload(); // the heatline scrubber
    _summary.reload(); // the first timeframe summary
  }

  @override
  void dispose() {
    _selection.removeListener(_onChange);
    _summary.removeListener(_onSummary);
    _cam.dispose();
    _summary.dispose();
    _selection.dispose();
    _timeline.dispose();
    _window.dispose();
    super.dispose();
  }

  void _onChange() => setState(() {});

  void _onSummary() {
    if (!mounted) return;
    setState(() {});
    if (_selection.mode == ViewMode.summary && _mapReady) _fitSummary();
  }

  void _onMapReady() {
    _mapReady = true;
    if (_selection.mode == ViewMode.summary) {
      _fitSummary();
    } else if (_detail?.geo != null) {
      _cam.animateTo(LatLng(_detail!.geo!.lat, _detail!.geo!.lon), 5);
    }
  }

  // --- focus / navigation ---------------------------------------------------------------

  void _select(String id, {LatLng? point}) {
    setState(() {
      _loadingDetail = true;
      _detailError = null;
      _detail = null;
    });
    if (point != null) _panelOnRight = point.longitude < 0;
    _selection.select(id);
    if (point != null && _mapReady) _cam.animateTo(point, 5);

    _api.event(id).then((d) {
      if (!mounted) return;
      setState(() {
        _detail = d;
        _loadingDetail = false;
      });
      if (d.geo != null) {
        _panelOnRight = d.geo!.lon < 0;
        if (_mapReady && point == null) {
          _cam.animateTo(LatLng(d.geo!.lat, d.geo!.lon), 5);
        }
      }
    }).catchError((e) {
      if (!mounted) return;
      setState(() {
        _detailError = e.toString();
        _loadingDetail = false;
      });
    });
  }

  void _clearSelection() {
    _selection.clear();
    setState(() => _detail = null);
    if (_mapReady) _fitSummary();
  }

  LatLng? _repPoint(String id) {
    final reps = _summary.summary?.representatives ?? const <SummaryRep>[];
    for (final r in reps) {
      if (r.id == id && r.geo != null) return LatLng(r.geo!.lat, r.geo!.lon);
    }
    return null;
  }

  // --- map data -------------------------------------------------------------------------

  /// Countries touched by the current summary (representatives + top places).
  List<Country> _involvedCountries() {
    if (_atlas.isEmpty) return const [];
    return _atlas.resolve(_summaryPoints());
  }

  /// country.id → event count, summed from the top places that fall inside it.
  Map<String, int> _countryWeights() {
    final s = _summary.summary;
    final out = <String, int>{};
    if (s == null || _atlas.isEmpty) return out;
    for (final p in s.topPlaces) {
      if (p.lat == null || p.lon == null) continue;
      final c = _atlas.countryAt(LatLng(p.lat!, p.lon!));
      if (c != null) out[c.id] = (out[c.id] ?? 0) + p.count;
    }
    return out;
  }

  /// Frame the actual event/place points (not country bounding boxes — those blow up for
  /// countries that straddle the antimeridian, e.g. Russia/Fiji/US-Aleutians).
  List<LatLng> _summaryPoints() {
    final s = _summary.summary;
    if (s == null) return const [];
    return [
      for (final r in s.representatives)
        if (r.geo != null) LatLng(r.geo!.lat, r.geo!.lon),
      for (final p in s.topPlaces)
        if (p.lat != null && p.lon != null) LatLng(p.lat!, p.lon!),
    ];
  }

  void _fitSummary() {
    final pts = _summaryPoints();
    if (pts.isNotEmpty) _cam.animateFit(pts);
  }

  (List<MapPin>, List<Country>, Map<String, int>) _mapData() {
    if (_selection.mode == ViewMode.detail) {
      final d = _detail;
      if (d?.geo == null) return (const [], const [], const {});
      final pt = LatLng(d!.geo!.lat, d.geo!.lon);
      final c = _atlas.isEmpty ? null : _atlas.countryAt(pt);
      return (
        [
          MapPin(
            id: d.id,
            point: pt,
            severity: d.severity,
            label: d.geoLabel,
            selected: true,
            onTap: () {},
          ),
        ],
        c != null ? [c] : const [],
        c != null ? {c.id: 1} : const {},
      );
    }
    // Summary mode: plot the representatives, draw every involved country.
    final reps = _summary.summary?.representatives ?? const <SummaryRep>[];
    final pins = [
      for (final r in reps)
        if (r.geo != null)
          MapPin(
            id: r.id,
            point: LatLng(r.geo!.lat, r.geo!.lon),
            severity: r.severity,
            label: r.geoLabel,
            imageUrl: r.heroMediaId != null ? _api.mediaUrl(r.heroMediaId!) : null,
            onTap: () => _select(r.id, point: LatLng(r.geo!.lat, r.geo!.lon)),
          ),
    ];
    return (pins, _involvedCountries(), _countryWeights());
  }

  // --- panel ----------------------------------------------------------------------------

  Widget _panel() {
    final Widget child;
    if (_selection.mode == ViewMode.detail) {
      if (_detailError != null) {
        child = Center(
          key: const ValueKey('detail-error'),
          child: Text('Failed to load: $_detailError'),
        );
      } else if (_detail == null || _loadingDetail) {
        child = const Center(
          key: ValueKey('detail-loading'),
          child: CircularProgressIndicator(),
        );
      } else {
        child = DetailPanel(
          key: ValueKey('detail-${_detail!.id}'),
          api: _api,
          detail: _detail!,
          onSelect: (id) => _select(id),
          onClose: _clearSelection,
        );
      }
    } else {
      child = SummaryPanel(
        key: const ValueKey('summary'),
        api: _api,
        summary: _summary.summary,
        loading: _summary.loading,
        error: _summary.error,
        onSelect: (id) => _select(id, point: _repPoint(id)),
      );
    }
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 350),
      switchInCurve: Curves.easeOutCubic,
      transitionBuilder: (c, anim) => FadeTransition(
        opacity: anim,
        child: SlideTransition(
          position: Tween<Offset>(
            begin: const Offset(0.06, 0),
            end: Offset.zero,
          ).animate(anim),
          child: c,
        ),
      ),
      child: child,
    );
  }

  // --- build ----------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final (pins, countries, weights) = _mapData();
    final map = SilhouetteMap(
      controller: _cam.mapController,
      countries: countries,
      pins: pins,
      countryWeights: weights,
      onMapReady: _onMapReady,
    );

    // MorphHost provides the flying-media overlay + the landing target the panel registers.
    return MorphHost(
      child: Builder(
        builder: (ctx) {
          final targetKey = MorphScope.maybeOf(ctx)?.targetKey ?? GlobalKey();
          return Scaffold(
            body: SafeArea(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final wide = constraints.maxWidth >= _kWideBreakpoint;
                  return wide ? _wide(map, targetKey) : _narrow(map, targetKey);
                },
              ),
            ),
          );
        },
      ),
    );
  }

  /// The panel content with an invisible landing box at the top where a flown image lands.
  Widget _panelWithTarget(GlobalKey targetKey) => Stack(
    children: [
      Positioned(
        top: 0,
        left: 0,
        right: 0,
        height: 210,
        child: IgnorePointer(child: SizedBox(key: targetKey)),
      ),
      Positioned.fill(child: _panel()),
    ],
  );

  Widget _searchBar() => Align(
    alignment: Alignment.topCenter,
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 560),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: TopSearchBar(
          api: _api,
          onSelect: (e) => _select(
            e.id,
            point: e.geo != null ? LatLng(e.geo!.lat, e.geo!.lon) : null,
          ),
        ),
      ),
    ),
  );

  /// The timeline as a vertical scroll/zoom bar pinned to the right edge.
  Widget _verticalTimeline({double width = 96}) => VerticalTimelineBar(
    controller: _timeline,
    selectedId: _selection.selectedEventId,
    onEventTap: (id) => _select(id),
    width: width,
  );

  /// A small floating pill over the map showing the level-of-detail readout (OVERVIEW vs a
  /// single EVENT), the current event count + range, and a one-tap way back to the overview.
  Widget _cockpitChip() {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final detail = _selection.mode == ViewMode.detail;
    final total = _summary.summary?.total;
    final range = '${formatYear(_window.t0)} → ${formatYear(_window.t1)}';
    final label = detail
        ? range
        : (total != null ? '$total events  ·  $range' : range);
    return Material(
      color: scheme.surface.withValues(alpha: 0.9),
      elevation: 2,
      borderRadius: BorderRadius.circular(24),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _modeBadge(detail),
            const SizedBox(width: 8),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 260),
              child: Text(
                label,
                style: theme.textTheme.labelMedium,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (detail) ...[
              const SizedBox(width: 4),
              TextButton.icon(
                onPressed: _clearSelection,
                style: TextButton.styleFrom(
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  visualDensity: VisualDensity.compact,
                ),
                icon: const Icon(Icons.grid_view_rounded, size: 16),
                label: const Text('Overview'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _modeBadge(bool detail) {
    final scheme = Theme.of(context).colorScheme;
    final color = detail ? scheme.primary : scheme.secondary;
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 250),
      child: Container(
        key: ValueKey(detail),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.16),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              detail ? Icons.place : Icons.travel_explore,
              size: 14,
              color: color,
            ),
            const SizedBox(width: 6),
            Text(
              detail ? 'EVENT' : 'OVERVIEW',
              style: TextStyle(
                color: color,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.8,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _wide(Widget map, GlobalKey targetKey) {
    final scheme = Theme.of(context).colorScheme;
    final mapStack = Expanded(
      child: Stack(
        children: [
          Positioned.fill(child: map),
          Positioned(left: 0, right: 0, top: 0, child: _searchBar()),
          Positioned(left: 12, top: 12, child: _cockpitChip()),
        ],
      ),
    );
    final panel = SizedBox(
      width: 420,
      child: Material(
        elevation: 3,
        color: scheme.surface,
        child: _panelWithTarget(targetKey),
      ),
    );
    final content = Row(
      children: _panelOnRight ? [mapStack, panel] : [panel, mapStack],
    );
    // Timeline pinned to the far-right edge as a vertical scroll/zoom bar.
    return Row(children: [Expanded(child: content), _verticalTimeline(width: 96)]);
  }

  /// Phone layout: the map fills with the morphing sheet over it; the timeline is the
  /// vertical bar on the right edge.
  Widget _narrow(Widget map, GlobalKey targetKey) {
    final detail = _selection.mode == ViewMode.detail;
    final body = LayoutBuilder(
      builder: (ctx, c) {
        final sheetH = (detail ? 0.62 : 0.40) * c.maxHeight;
        return Stack(
          children: [
            Positioned.fill(child: map),
            Positioned(left: 0, right: 0, top: 0, child: _searchBar()),
            Positioned(left: 8, top: 8, child: _cockpitChip()),
            AnimatedPositioned(
              duration: const Duration(milliseconds: 350),
              curve: Curves.easeOutCubic,
              left: 0,
              right: 0,
              bottom: 0,
              height: sheetH,
              child: _sheet(targetKey, detail),
            ),
          ],
        );
      },
    );
    return Row(children: [Expanded(child: body), _verticalTimeline(width: 60)]);
  }

  Widget _sheet(GlobalKey targetKey, bool detail) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      elevation: 10,
      color: scheme.surface,
      clipBehavior: Clip.antiAlias,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        children: [
          GestureDetector(
            onTap: detail ? _clearSelection : null,
            behavior: HitTestBehavior.opaque,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Column(
                children: [
                  Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                      color: scheme.onSurfaceVariant.withValues(alpha: 0.4),
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  if (detail)
                    Text(
                      'tap to return to the overview',
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                ],
              ),
            ),
          ),
          Expanded(child: _panelWithTarget(targetKey)),
        ],
      ),
    );
  }
}
