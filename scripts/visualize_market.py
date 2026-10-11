"""Render one saved daily hit market as a standalone HTML report; no network."""
import argparse
from bisect import bisect_right
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
import hashlib
import json
from pathlib import Path


def epoch(value):
    return int(datetime.fromisoformat(value).timestamp())


def usable_points(history, start, end):
    points = {}
    for segment in history.get('granular', []):
        if not segment.get('complete'):
            continue
        for p in segment['points']:
            if (p.get('forecasting_candidate') and p['resolution_seconds'] == 300
                    and start <= p['timestamp'] < p['bucket_end'] <= end):
                points[(p['timestamp'], p['bucket_end'])] = p
    return sorted(points.values(), key=lambda p: p['bucket_end'])


def join_candles(points, candles):
    """Use only candles completed before each market bucket end."""
    candles = sorted(candles, key=lambda c: c['close_time_ms'])
    times = [c['close_time_ms'] for c in candles]
    rows = []
    for p in points:
        i = bisect_right(times, p['bucket_end'] * 1000 - 1) - 1
        rows.append({'time': p['bucket_end'], 'price': p['price'],
                     'btc': candles[i]['close'] if i >= 0 and
                     p['bucket_end'] * 1000 - times[i] <= 60000 else None})
    return rows


def distance_rows(rows, candles, semantics):
    """Track barrier status using only completed candles available at each time."""
    threshold = Decimal(semantics['threshold'])
    start, end = epoch(semantics['window_start']), epoch(semantics['window_end'])
    upward = semantics['kind'] == 'window_high'
    candles = sorted(candles, key=lambda c: c['close_time_ms'])
    i, expected, reached, contiguous = 0, start * 1000, False, True
    result = []
    for row in rows:
        while i < len(candles) and candles[i]['close_time_ms'] < row['time'] * 1000:
            c = candles[i]
            contiguous = contiguous and c['open_time_ms'] == expected and c['close_time_ms'] == expected + 59999
            expected = c['open_time_ms'] + 60000
            value = Decimal(c['high' if upward else 'low'])
            reached = reached or (value >= threshold if upward else value <= threshold)
            i += 1
        status = 'after_hit' if reached else 'before_hit' if contiguous and expected == row['time'] * 1000 else 'unknown'
        spot = Decimal(row['btc']) if row['btc'] is not None else None
        gap = ((threshold / spot - 1) if upward else (1 - threshold / spot)) * 100 if spot else None
        result.append(dict(row, distance_pct=str(gap) if gap is not None else None,
                           hours_remaining=(end-row['time'])/3600, barrier_status=status))
    return result


def first_hit(candles, semantics):
    """Return the first completed crossing candle, not a venue resolution time."""
    threshold = Decimal(semantics['threshold'])
    upward = semantics['kind'] == 'window_high'
    for c in sorted(candles, key=lambda c: c['close_time_ms']):
        value = Decimal(c['high' if upward else 'low'])
        if value >= threshold if upward else value <= threshold:
            return (c['close_time_ms'] + 1) / 1000
    return None


def venue_badge(label):
    resolution = label.get('resolution') or {}
    if resolution.get('status') == 'resolved' and str(resolution.get('price')) == '1000000000000000000':
        return '<span class="yes-badge">✓ Venue recorded YES</span>'
    return ''


def scatter(rows):
    eligible = [(i, r) for i, r in enumerate(rows) if r['distance_pct'] is not None and r['barrier_status'] != 'unknown']
    gaps = [float(r['distance_pct']) for _, r in eligible]
    low, high = min(gaps+[0]), max(gaps+[0])
    padding = max((high-low)*0.08, 0.1)
    low, high = low-padding, high+padding
    panels = []
    for status, title in [('before_hit', 'Before a known hit'), ('after_hit', '✓ YES threshold reached · observations after the hit')]:
        parts = ['<svg viewBox="0 0 1000 300" role="img">']
        for tick in range(5):
            x, value = 90+tick*205, low+(high-low)*tick/4
            parts.append(f'<text x="{x}" y="253" text-anchor="middle">{value:.2f}%</text>')
            y = 230-tick*50
            parts.append(f'<path d="M90 {y}H910" stroke="#e2e8f0"/><text x="82" y="{y+4}" text-anchor="end">{tick/4:.2f}</text>')
        parts.append('<text x="90" y="18">YES price</text><text x="500" y="280" text-anchor="middle">Move needed to reach threshold (% of current BTC price)</text>')
        selected = [(i,r) for i,r in eligible if r['barrier_status'] == status]
        for i, r in selected:
            x, y = 90+(float(r['distance_pct'])-low)/(high-low)*820, 230-float(r['price'])*200
            color = f'hsl({30+220*min(24,max(0,r["hours_remaining"]))/24:.0f},75%,45%)'
            tip = f'{datetime.fromtimestamp(r["time"],timezone.utc).isoformat()} · distance {float(r["distance_pct"]):.2f}% · YES {r["price"]} · {r["hours_remaining"]:.2f}h remaining'
            parts.append(f'<circle id="scatter-{i}" data-row="{i}" cx="{x}" cy="{y}" r="4" fill="{color}" fill-opacity="0.7" style="cursor:pointer"><title>{escape(tip)}</title></circle>')
        if not selected:
            parts.append('<text x="500" y="130" text-anchor="middle">No eligible observations in this group</text>')
        parts.append('</svg>')
        panels.append(f'<h3>{title} · {len(selected)} points</h3>'+''.join(parts))
    excluded = len(rows)-len(eligible)
    return ''.join(panels)+f'<p>{excluded} observations omitted because spot or barrier status is unknown.</p>'


def chart(points, start, end, low, high, color, threshold=None, max_gap=300, overlay=None):
    x = lambda t: 90 + (t - start) / (end - start) * 820
    y = lambda v: 230 - (float(v) - low) / (high - low) * 200
    parts = ['<svg viewBox="0 -48 1000 333" role="img">']
    for i in range(5):
        value = low + (high - low) * i / 4
        parts.append(f'<path d="M90 {y(value)}H910" stroke="#e2e8f0"/><text x="82" y="{y(value)+4}" text-anchor="end">{value:,.2f}</text>')
    for hours in range(0, 25, 4):
        t = start + hours * 3600
        if t <= end:
            label = datetime.fromtimestamp(t, timezone.utc).strftime('%H:%M')
            parts.append(f'<text x="{x(t)}" y="255" text-anchor="middle">{label}</text>')
    if threshold is not None:
        parts.append(f'<path d="M90 {y(threshold)}H910" stroke="#dc2626" stroke-dasharray="6 4"/>')
    previous = None
    for t, value in points:
        if value is None:
            previous = None
            continue
        if previous and t - previous[0] <= max_gap:
            parts.append(f'<path d="M{x(previous[0])} {y(previous[1])}L{x(t)} {y(value)}" stroke="{color}" fill="none" stroke-width="2"/>')
        label = datetime.fromtimestamp(t, timezone.utc).isoformat() + f' · {float(value):,.4f}'
        parts.append(f'<circle cx="{x(t)}" cy="{y(value)}" r="3" fill="{color}"><title>{label}</title></circle>')
        previous = (t, value)
    if overlay is not None:
        parts.append('<text x="90" y="16">BTC/USDT · left axis</text><text x="910" y="16" text-anchor="end">YES price · right axis</text>')
        for i in range(5):
            parts.append(f'<text x="922" y="{230-i*50+4}">{i/4:.2f}</text>')
        previous = None
        for t, value in overlay:
            py = 230 - float(value) * 200
            if previous and t - previous[0] <= 300:
                parts.append(f'<path d="M{x(previous[0])} {previous[1]}L{x(t)} {py}" stroke="#0f766e" fill="none" stroke-width="2"/>')
            parts.append(f'<circle cx="{x(t)}" cy="{py}" r="3" fill="#0f766e"><title>YES {value}</title></circle>')
            previous = (t, py)
        parts.append('<line id="cursor" y1="30" y2="230" stroke="#64748b" stroke-dasharray="3 3"/><circle id="btc-marker" r="6" fill="#2563eb" stroke="white" stroke-width="2"/><circle id="yes-marker" r="6" fill="#0f766e" stroke="white" stroke-width="2"/>')
    if overlay is not None:
        parts.append('<rect x="90" y="-43" width="320" height="45" rx="5" fill="white" stroke="#e2e8f0"/><text id="btc-label" style="fill:#2563eb;font-size:14px;font-weight:600;paint-order:stroke;stroke:#f8fafc;stroke-width:4px;stroke-linejoin:round"></text><text id="yes-label" style="fill:#0f766e;font-size:14px;font-weight:600;paint-order:stroke;stroke:#f8fafc;stroke-width:4px;stroke-linejoin:round"></text>')
    parts.append('</svg>')
    return ''.join(parts)


def render(folder, market_id, output, navigation=None):
    markets = json.loads((folder / 'markets.json').read_text())
    market = next(m for m in markets if m['market_id'] == market_id)
    sem = market['semantics']
    if not sem or sem['timeframe'] != 'daily' or sem['kind'] not in ('window_high', 'window_low'):
        raise ValueError('This first report supports daily hit markets only')
    start, end = epoch(sem['window_start']), epoch(sem['window_end'])
    labels = {m['market_id']: m for m in json.loads((folder / 'labels.json').read_text())['markets']}
    histories = {m['market_id']: m for m in json.loads((folder / 'prices.json').read_text())['markets']}
    candles = [c for c in json.loads((folder / 'btc.json').read_text())['candles']
               if start * 1000 <= c['open_time_ms'] and c['close_time_ms'] < end * 1000]
    candles.sort(key=lambda c: c['open_time_ms'])
    if not candles or candles[0]['open_time_ms'] != start * 1000:
        raise ValueError('Missing opening candle; cannot establish opening distance')
    complete = (len(candles) == (end-start)//60 and all(c['open_time_ms'] == (start+i*60)*1000
                and c['close_time_ms'] == (start+(i+1)*60)*1000-1 for i,c in enumerate(candles)))
    points = usable_points(histories[market_id], start, end)
    if not points:
        raise ValueError('No usable five-minute history within the window')
    rows = distance_rows(join_candles(points, candles), candles, sem)
    distance_chart = scatter(rows)
    opening = Decimal(candles[0]['open'])
    threshold = Decimal(sem['threshold'])
    field = 'high' if sem['kind'] == 'window_high' else 'low'
    hits = [c for c in candles if (Decimal(c[field]) >= threshold if field == 'high' else Decimal(c[field]) <= threshold)]
    hit_text = ('Observed threshold crossing in candle beginning ' + datetime.fromtimestamp(hits[0]['open_time_ms']/1000, timezone.utc).isoformat()) if hits else ('No crossing in the complete saved window' if complete else 'No crossing observed; candle coverage incomplete')
    table = []
    comparisons = []
    for m in markets:
        s = m['semantics']
        if not s or s['window_start'] != sem['window_start'] or s['window_end'] != sem['window_end']:
            continue
        ps = usable_points(histories[m['market_id']], start, end)
        values = [Decimal(p['price']) for p in ps]
        distance = (Decimal(s['threshold']) / opening - 1) * 100
        comparisons.append((abs(distance), m, ps))
        price_range = f'{min(values):.4f}–{max(values):.4f}' if values else 'Missing'
        table.append((abs(distance), f'<tr><td>{escape(m["title"])}</td><td>{distance:+.2f}%</td><td>{price_range}</td><td>{len(ps)}</td></tr>'))
    low = min(float(c['low']) for c in candles)
    high = max(float(c['high']) for c in candles)
    lower, upper = min(low,float(threshold))-200, max(high,float(threshold))+200
    hit_time = first_hit(candles, sem)
    status_badge = venue_badge(labels.get(market_id, {}))
    btc_chart = chart([(c['close_time_ms']/1000,c['close']) for c in candles],start,end,lower,upper,'#2563eb',threshold,max_gap=60,overlay=[(r['time'],r['price']) for r in rows])
    if hit_time is not None:
        hit_x = 90+(hit_time-start)/(end-start)*820
        marker = f'<rect x="{hit_x}" y="30" width="{910-hit_x}" height="200" fill="#16a34a" opacity="0.045"/><line x1="{hit_x}" x2="{hit_x}" y1="30" y2="230" stroke="#86a995" stroke-dasharray="4 5"/><text x="910" y="-15" text-anchor="end" style="fill:#36704d">✓ YES threshold reached {datetime.fromtimestamp(hit_time,timezone.utc).strftime("%H:%M")} UTC</text>'
        btc_chart = btc_chart.replace('<svg viewBox="0 -48 1000 333" role="img">','<svg viewBox="0 -48 1000 333" role="img">'+marker)
    colors = ['#2563eb','#0f766e','#d97706','#9333ea','#db2777','#64748b']
    comparison_sections = []
    for kind, name in [('window_high','Reaching · upward thresholds'), ('window_low','Dipping · downward thresholds')]:
        group = [item for item in comparisons if item[1]['semantics']['kind'] == kind]
        comparison_parts = ['<svg viewBox="0 0 1000 285" role="img">']
        legend = []
        for color, (_, m, ps) in zip(colors, sorted(group, key=lambda item: item[0])[:6]):
            previous = None
            for point in ps:
                t, value = point['bucket_end'], float(point['price'])
                x, y = 90+(t-start)/(end-start)*820, 230-value*200
                if previous and t-previous[0] <= 300:
                    comparison_parts.append(f'<path d="M{previous[1]} {previous[2]}L{x} {y}" stroke="{color}" fill="none" stroke-width="2"/>')
                previous = (t,x,y)
            comparison_hit = first_hit(candles, m['semantics'])
            hit_note = ''
            if comparison_hit is not None:
                hx=90+(comparison_hit-start)/(end-start)*820
                hit_note = ' · threshold reached '+datetime.fromtimestamp(comparison_hit,timezone.utc).strftime('%H:%M')+' UTC'
                comparison_parts.append(f'<line x1="{hx}" x2="{hx}" y1="30" y2="230" stroke="{color}" stroke-opacity="0.25" stroke-dasharray="3 5"/><circle cx="{hx}" cy="24" r="4" fill="{color}"><title>{escape(m["title"]+hit_note)}</title></circle>')
            badge = venue_badge(labels.get(m['market_id'], {}))
            legend.append(f'<span style="color:{color}">{escape(m["title"])}</span>{badge}<small>{hit_note}</small>')
        for tick in range(5):
            comparison_parts.append(f'<text x="82" y="{234-tick*50}" text-anchor="end">{tick/4:.2f}</text>')
        for hours in range(0,25,4):
            t=start+hours*3600
            if t<=end:comparison_parts.append(f'<text x="{90+(t-start)/(end-start)*820}" y="255" text-anchor="middle">{datetime.fromtimestamp(t,timezone.utc).strftime("%H:%M")}</text>')
        comparison_parts.append('</svg>')
        comparison_sections.append(f'<h3>{name}</h3>'+''.join(comparison_parts)+'<p>'+'<br>'.join(legend)+'</p>')
    comparison_chart = ''.join(comparison_sections)
    selectors = ''
    if navigation:
        event_options = ''.join(f'<option value="{escape(item["path"])}" {"selected" if item["id"]==folder.name else ""}>{escape(item["title"])}</option>' for item in navigation['events'])
        market_options = ''.join(f'<option value="{escape(item["path"])}" {"selected" if item["id"]==market_id else ""}>{escape(item["title"])}</option>' for item in navigation['markets'][folder.name])
        selectors = f'<p><label>Event <select onchange="location.href=this.value">{event_options}</select></label></p><p><label>Market <select onchange="location.href=this.value">{market_options}</select></label></p>'
    distance = (threshold/opening-1)*100
    title = escape(market['title'])
    provenance = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                  for name in ('markets.json', 'prices.json', 'btc.json', 'labels.json')}
    provenance['script'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px system-ui;max-width:1080px;margin:35px auto;padding:0 20px;color:#172033}}svg{{width:100%;background:#f8fafc}}svg text{{font:12px system-ui;fill:#475569}}table{{border-collapse:collapse;width:100%}}td,th{{padding:9px;border-bottom:1px solid #ddd;text-align:left}}.note{{color:#475569}}.yes-badge{{display:inline-block;margin:0 8px;padding:2px 7px;border-radius:5px;background:#edf7ef;color:#36704d;font-size:13px}}input{{width:100%}}</style>
{selectors}<h1>{title}</h1>{status_badge}<p>{escape(sem["window_start"])} to {escape(sem["window_end"])} · UTC. Opening BTC/USDT: {opening:,.2f}. Threshold: {threshold:,.0f} ({distance:+.2f}% from opening).</p>
<h2>BTC and YES price</h2><p><span style="color:#2563eb">Blue: BTC/USDT one-minute closes (left axis)</span> · <span style="color:#0f766e">Green: YES five-minute price (right axis, 0–1)</span> · Red dashed: hit threshold. The source uses candle {field}s; closes alone do not establish a hit.</p>{btc_chart}
<p>Move the slider to inspect each five-minute observation. The vertical marker shows its bucket end; dots highlight YES and the latest completed BTC candle. The chart keeps the full day visible. Missing buckets remain disconnected.</p><label for="slider">Observation time</label><input id="slider" type="range" min="0" max="{len(rows)-1}" value="0"><p id="detail" aria-live="polite"></p>
<p>{escape(hit_text)}. Stored BTC range: {low:,.2f}–{high:,.2f}. Valid market buckets: {len(points)} / {(end-start)//300} possible daily slots.</p>
<h2>YES price versus distance to threshold</h2><p>Each dot is one five-minute bucket. Positive distance means BTC still needs to move toward the barrier; negative means spot is beyond it. An earlier hit stays a hit even if spot moves back.</p>
<p><span style="color:hsl(250,75%,45%)">Blue/purple: 24 hours remaining</span> → <span style="color:hsl(140,75%,45%)">green: 12 hours</span> → <span style="color:hsl(30,75%,45%)">orange: near window end</span>. Hover for details; click a dot to move the time slider. The slider outlines the selected dot.</p>{distance_chart}
<p class="note">Distance and remaining time describe the same day's correlated observations; this view does not establish predictive power. Barrier status uses completed source candles and remains conditional on the stored rules.</p>
<h2>Nearby markets in this event</h2><p>Upward and downward hit markets are shown separately, with up to six thresholds nearest the opening spot price in each group. Each line uses its own YES history; gaps remain disconnected. These are different path conditions. Small dots above the plot and faint dashed lines mark observed threshold hits; they are annotations, not price observations.</p>{comparison_chart}
<h2>Other thresholds in this event</h2><p>Sorted by absolute distance from the opening spot price. Price ranges use the entire day and are descriptive only; they must not be used to select markets for a historical prediction.</p>
<table><thead><tr><th>Market</th><th>Opening distance</th><th>YES range</th><th>5-minute buckets</th></tr></thead><tbody>{''.join(row for _,row in sorted(table))}</tbody></table>
<p class="note">Market {market_id}; source: {escape(str(folder))}. Nearness to spot is a useful starting point, but direction, time remaining, volatility and whether the barrier has already been hit also matter. No distance filter is imposed.</p>
<p class="note">Exploratory description only. Price aggregation and historical rule versions remain unverified. Zero-width and incomplete-segment points are excluded. YES badges describe the venue record; historical rule-version flags still require review. Hit markers use the end of the first crossing Binance candle, not the venue resolution time. No accepted settlement label, executable quote, forecast or backtest is presented.</p>
<details><summary>Input provenance · report schema 2</summary><pre>{escape(json.dumps(provenance, indent=2))}</pre></details>
<script>const rows={json.dumps(rows)};const slider=document.getElementById('slider');
let selectedDot=null;
function show(){{
 if(selectedDot){{selectedDot.removeAttribute('stroke');selectedDot.setAttribute('r',4);}}
 selectedDot=document.getElementById('scatter-'+slider.value);
 if(selectedDot){{selectedDot.setAttribute('stroke','#111827');selectedDot.setAttribute('stroke-width',2);selectedDot.setAttribute('r',7);}}
 const r=rows[Number(slider.value)],x=90+(r.time-{start})/({end}-{start})*820;
 const cursor=document.getElementById('cursor');cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);
 const yes=document.getElementById('yes-marker');yes.setAttribute('cx',x);yes.setAttribute('cy',230-Number(r.price)*200);
 const btc=document.getElementById('btc-marker');btc.style.display=r.btc===null?'none':'';
 const yesY=230-Number(r.price)*200;
 const btcY=r.btc===null?null:230-(Number(r.btc)-{lower})/({upper}-{lower})*200;
 if(btcY!==null){{btc.setAttribute('cx',x);btc.setAttribute('cy',btcY);}}
 function label(id,text,y){{
  const el=document.getElementById(id);el.textContent=text;
  el.setAttribute('x',102);el.setAttribute('y',y);el.setAttribute('text-anchor','start');
 }}
 label('yes-label','YES '+Number(r.price).toFixed(4),-8);
 label('btc-label',r.btc===null?'BTC missing or stale':'BTC '+Number(r.btc).toLocaleString('en-US',{{minimumFractionDigits:2,maximumFractionDigits:2}})+' USDT',-26);
 document.getElementById('detail').textContent=new Date(r.time*1000).toISOString()+' · YES '+r.price+' · BTC/USDT '+(r.btc??'missing or stale');
}}slider.addEventListener('input',show);
document.querySelectorAll('[data-row]').forEach(dot=>dot.addEventListener('click',()=>{{slider.value=dot.dataset.row;show();}}));show();</script></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)
    print(f'{output}: {len(points)} market buckets; {len(candles)} BTC candles; complete candle window={complete}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all-daily', action='store_true', help='Build event/market selectors and reports for daily markets')
    parser.add_argument('--event', default='1151848')
    parser.add_argument('--market', default='5422669')
    parser.add_argument('--data', type=Path, default=Path('data/bitcoin'))
    parser.add_argument('--output', type=Path, default=Path('data/analysis/market-preview.html'))
    args = parser.parse_args()
    if not args.all_daily:
        render(args.data / args.event, args.market, args.output)
        return
    catalog = json.loads((args.data/'catalog.json').read_text())
    navigation = {'events': [], 'markets': {}}
    jobs = []
    for event in catalog['events']:
        folder = args.data / str(event['id'])
        markets = json.loads((folder/'markets.json').read_text())
        histories = {m['market_id']:m for m in json.loads((folder/'prices.json').read_text())['markets']}
        available = []
        for m in markets:
            sem=m['semantics']
            if not sem or sem['timeframe']!='daily' or sem['kind'] not in ('window_high','window_low'):
                continue
            if not usable_points(histories[m['market_id']],epoch(sem['window_start']),epoch(sem['window_end'])):
                continue
            filename=f'{event["id"]}-{m["market_id"]}.html'
            available.append({'id':m['market_id'],'title':m['title'],'path':filename})
            jobs.append((folder,m['market_id'],filename))
        if available:
            navigation['events'].append({'id':str(event['id']),'title':event['title'],'path':available[0]['path']})
            navigation['markets'][str(event['id'])]=available
    for folder, market_id, filename in jobs:
        render(folder,market_id,args.output.parent/filename,navigation)
    preferred=f'{args.event}-{args.market}.html'
    if jobs:
        selected=preferred if any(job[2]==preferred for job in jobs) else jobs[0][2]
        args.output.write_text((args.output.parent/selected).read_text())
    print(f'Built {len(jobs)} market reports across {len(navigation["events"])} daily events; entry: {args.output}')


if __name__ == '__main__':
    main()
