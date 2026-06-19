import 'package:chronos_admin/api/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('OverviewView parses components, counts, and runs', () {
    final o = OverviewView.fromJson({
      'counts': {'events': 255, 'entities': 40, 'relations': 12, 'media': 8},
      'components': [
        {
          'id': 'agent:enrich',
          'kind': 'agent',
          'title': 'Enricher',
          'description': 'LLM enrichment',
          'capabilities': ['llm-call'],
          'actions': ['enable', 'disable', 'run-now'],
          'config_prefix': 'agents.enrich',
          'enabled': true,
          'health': {'status': 'ok', 'runs': 3, 'success_rate': 1.0, 'last_status': 'ok'},
        },
      ],
      'recent_runs': [
        {
          'id': 'r1',
          'component_id': 'agent:enrich',
          'command': 'enrich',
          'status': 'ok',
          'started_at': '2026-06-19T10:00:00Z',
          'finished_at': '2026-06-19T10:00:05Z',
          'stats': {'enriched': 5},
        },
      ],
    });

    expect(o.counts['events'], 255);
    expect(o.components.single.enabled, true);
    expect(o.components.single.health.status, 'ok');
    expect(o.recentRuns.single.command, 'enrich');
    expect(o.recentRuns.single.stats!['enriched'], 5);
  });

  test('ConfigEntry parses spec metadata + constraints', () {
    final e = ConfigEntry.fromJson({
      'key': 'agents.enrich.batch_size',
      'type': 'int',
      'scope': 'agent:enrich',
      'label': 'Batch size',
      'help': 'how many per run',
      'value': 20,
      'default': 20,
      'minimum': 1,
      'maximum': 200,
      'component_id': 'agent:enrich',
    });
    expect(e.type, 'int');
    expect(e.minimum, 1);
    expect(e.maximum, 200);
    expect(e.value, 20);
  });

  test('StorageView parses breakdowns and bytes', () {
    final s = StorageView.fromJson({
      'media_by_status': {'stored': 3, 'external': 5},
      'media_by_disposition': {'archive': 6, 'link': 2},
      'media_stored_bytes': 1048576,
      'totals': {'events': 255},
    });
    expect(s.mediaByStatus['stored'], 3);
    expect(s.mediaStoredBytes, 1048576);
  });
}
