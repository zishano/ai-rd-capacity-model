"""Input file and evidence validation for the capacity model. Python 3.9+."""
import copy
import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

LEVELS = ('AL3', 'AL4', 'AL5')
DEFAULT_CONFIG = Path(__file__).resolve().parent / 'config' / 'assumptions.json'
SCENARIO_KEYS = set('agents duration duty exec_duty resident input output cache tools fanout depth c m s context qin qout peak head g h eg eh evalreps success retry valid synth ckpt dataset retention f keep private review log alpha_c alpha_m alpha_s'.split())
FIXED_KEYS = set('people gpu_price cpu_price ram_price ssd_price fs_price obj_price backup_price net_price control_price human_price base_gb backup_frac io_blocks io_mb egress_frac stg_read q_gpu q_infer trans startsec recovery weight_b mem_gb hbmfrac tp gpu_active_kw gpu_idle_kw pue steps_h grad_gb h2d_gb'.split())
SETTING_KEYS = set('years reference_year layer_count model_width kv_heads head_dimension precision_bytes kv_sequences lifecycle_events auth_events billing_window queue_baseline queue_grid sandbox_grid sensitivity cold_start_vcpu'.split())


def required_keys(obj, keys, path, exact=False):
    if not isinstance(obj, dict):
        raise ValueError(f'{path}: expected a JSON object')
    missing = set(keys) - obj.keys()
    if missing:
        raise ValueError(f'{path}: missing {sorted(missing)}')
    extra = obj.keys() - set(keys)
    if exact and extra:
        raise ValueError(f'{path}: unknown {sorted(extra)}')


def read_json(raw):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f'Duplicate JSON key: {key}')
            obj[key] = value
        return obj
    return json.loads(raw, object_pairs_hook=unique)


def number(value, path, *, positive=False, integer=False, maximum=None):
    if (type(value) not in (float, int) or not math.isfinite(value)
            or value < 0 or (positive and value == 0)
            or (integer and int(value) != value)
            or (maximum is not None and value > maximum)):
        raise ValueError(f'{path}: invalid numeric value {value!r}')


def text(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{path}: expected nonempty text')


def iso_date(value, path):
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError(f'{path}: expected YYYY-MM-DD') from None


def url(value, path):
    if not isinstance(value, str) or urlsplit(value).scheme not in ('http', 'https') or not urlsplit(value).netloc:
        raise ValueError(f'{path}: expected an HTTP(S) URL')


def check_evidence(ev, path, sub_key=None, allowed_scopes=()):
    required_keys(ev, ('kind', 'as_of', 'scope', 'rationale', 'calibration', 'references'), path)
    for key in ('kind', 'scope', 'rationale', 'calibration'):
        text(ev[key], f'{path}.{key}')
    if ev['kind'] not in ('A','B','C','brief','spec','formula','definition'):
        raise ValueError(f"{path}.kind: unknown evidence type {ev['kind']!r}")
    iso_date(ev['as_of'], f'{path}.as_of')
    if not isinstance(ev['references'], list):
        raise ValueError(f'{path}.references: expected list')
    for i, ref in enumerate(ev['references']):
        p = f'{path}.references[{i}]'
        required_keys(ref, ('title', 'url', 'role'), p)
        text(ref['title'], f'{p}.title')
        text(ref['role'], f'{p}.role')
        url(ref['url'], f'{p}.url')
    if ev['kind'] in ('A', 'B') and not any(r['role'] == 'direct' for r in ev['references']):
        raise ValueError(f'{path}: evidence A/B requires a direct source')
    for field in ('by_level','by_year'):
        if field not in ev:
            continue
        parts = ev[field]
        if field != sub_key or not isinstance(parts, dict) or set(parts) - set(allowed_scopes):
            raise ValueError(f'{path}.{field}: invalid evidence scope')
        base = {k: v for k, v in ev.items() if k != field}
        for name, update in parts.items():
            if not isinstance(update, dict):
                raise ValueError(f'{path}.{field}.{name}: expected an object')
            check_evidence({**base, **update}, f'{path}.{field}.{name}')


def check_value(group, key, value, path):
    if group == 'scenarios':
        pos = key in {'agents','duration','success','valid','qin','qout','head','g','h','eg','eh','evalreps','context','alpha_c','alpha_m','alpha_s'}
        fraction = key in {'duty','exec_duty','resident','cache','fanout','success','retry','valid','f','private'}
        whole = key in {'g','eg','evalreps','context'}
    else:
        pos = key in {'people','tp','mem_gb','q_infer','q_gpu','hbmfrac','weight_b'}
        fraction = key in {'q_infer','q_gpu','hbmfrac','backup_frac','egress_frac'}
        whole = key == 'tp'
    number(value, path, positive=pos, integer=whole, maximum=1 if fraction else None)
    if key in ('peak', 'pue') and value < 1:
        raise ValueError(f'{path}: must be at least 1')


def setting_values(config):
    return {k: entry['value'] for k, entry in config['settings'].items()}


def validate_config(config):
    required_keys(config, ('schema_version','as_of','sources','scenarios','fixed','settings'), 'config')
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('Unsupported config.schema_version')
    iso_date(config['as_of'], 'as_of')
    required_keys(config['sources'], (), 'sources')
    for key, value in config['sources'].items():
        url(value, f'sources.{key}')
    for group, keys in [('scenarios', SCENARIO_KEYS), ('fixed', FIXED_KEYS), ('settings', SETTING_KEYS)]:
        required_keys(config[group], keys, group, exact=True)
        for key, entry in config[group].items():
            path = f'{group}.{key}'
            value_field = 'values' if group == 'scenarios' else 'value'
            required_keys(entry, ('label','unit',value_field,'evidence'), path)
            text(entry['label'], f'{path}.label')
            text(entry['unit'], f'{path}.unit')
            if group == 'scenarios':
                check_evidence(entry['evidence'], f'{path}.evidence', 'by_level', LEVELS)
            elif group == 'settings' and key == 'years':
                required_keys(entry['value'], (), f'{path}.value')
                check_evidence(entry['evidence'], f'{path}.evidence', 'by_year', entry['value'])
            else:
                check_evidence(entry['evidence'], f'{path}.evidence')
            if group == 'settings':
                continue
            required_keys(entry, ('low','high','reason'), path)
            text(entry['reason'], f'{path}.reason')
            number(entry['low'], f'{path}.low')
            number(entry['high'], f'{path}.high')
            if entry['low'] > entry['high']:
                raise ValueError(f'{path}: pressure range is reversed')
            if group == 'scenarios':
                required_keys(entry['values'], LEVELS, f'{path}.values', exact=True)
                for level, value in entry['values'].items():
                    check_value(group, key, value, f'{path}.values.{level}')
            else:
                check_value(group, key, entry['value'], f'{path}.value')
    settings = setting_values(config)
    for key in ('reference_year','layer_count','model_width','kv_heads','head_dimension'):
        number(settings[key], f'settings.{key}', positive=True, integer=True)
    for key in ('precision_bytes','kv_sequences'):
        number(settings[key], f'settings.{key}', positive=True)
    for key in ('cold_start_vcpu','auth_events'):
        number(settings[key], f'settings.{key}')
    years = settings['years']
    required_keys(years, (), 'settings.years')
    for year, scale in years.items():
        if not (isinstance(year, str) and len(year) == 4 and year.isascii() and year.isdecimal()):
            raise ValueError(f'settings.years: invalid year {year!r}')
        number(scale, f'settings.years.{year}', positive=True)
    if str(settings['reference_year']) not in years:
        raise ValueError('settings.reference_year must be included in settings.years')
    for key, fields in [('lifecycle_events', ('create_destroy','restore')),
                        ('billing_window', ('month_days','year_days')),
                        ('queue_baseline', ('slots','gpu_per_job','hours_per_job'))]:
        required_keys(settings[key], fields, f'settings.{key}', exact=True)
        for sub, value in settings[key].items():
            number(value, f'settings.{key}.{sub}', positive=key != 'lifecycle_events',
                   integer=sub in ('slots','gpu_per_job'))
    for key in ('sandbox_grid','queue_grid'):
        if not isinstance(settings[key], list) or not settings[key]:
            raise ValueError(f'settings.{key}: expected a nonempty list')
        for i, value in enumerate(settings[key]):
            number(value, f'settings.{key}[{i}]', integer=key == 'sandbox_grid')
    sensitivity = settings['sensitivity']
    required_keys(sensitivity, (), 'settings.sensitivity')
    for key, test in sensitivity.items():
        path = f'settings.sensitivity.{key}'
        if key not in SCENARIO_KEYS | FIXED_KEYS:
            raise ValueError(f'{path}: unknown parameter')
        required_keys(test, ('mode','points'), path, exact=True)
        if test['mode'] not in ('multiply','set') or not isinstance(test['points'], list) or not test['points']:
            raise ValueError(f'{path}: specify mode set/multiply and nonempty points')
        for i, value in enumerate(test['points']):
            number(value, f'{path}.points[{i}]')


def load_config(path=DEFAULT_CONFIG):
    config = read_json(Path(path).read_bytes())
    validate_config(config)
    return config


def effective_config(config, overrides=None):
    """Apply temporary scenarios without attributing their values to the original sources."""
    if overrides is None or overrides == {}:
        return config
    if not isinstance(overrides, dict):
        raise ValueError('overrides: expected a JSON object')
    effective = copy.deepcopy(config)
    for group, changes in overrides.items():
        if group not in (*LEVELS, 'fixed', 'years') or not isinstance(changes, dict):
            raise ValueError(f'Invalid override group {group!r}')
        for key, value in changes.items():
            if group == 'years':
                entry = effective['settings']['years']
                entry['value'][str(key)] = value
            else:
                section = 'fixed' if group == 'fixed' else 'scenarios'
                if key not in effective[section]:
                    raise ValueError(f'Unknown override: {group}.{key}')
                entry = effective[section][key]
                if group == 'fixed':
                    entry['value'] = value
                else:
                    entry['values'][group] = value
            replacement = dict(kind='C', as_of=config['as_of'], scope='本次运行的临时覆盖值',
                               rationale='按本次运行指定的覆盖配置复算。',
                               calibration=entry['evidence']['calibration'], references=[])
            if group in LEVELS:
                entry['evidence'].setdefault('by_level', {})[group] = replacement
            elif group == 'years':
                entry['evidence'].setdefault('by_year', {})[str(key)] = replacement
            else:
                entry['evidence'] = replacement
    validate_config(effective)
    return effective
