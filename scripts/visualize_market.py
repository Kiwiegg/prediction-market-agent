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


def render(folder, market_id, output):
    markets = json.loads((folder / 'markets.json').read_text())
    market = next(m for m in markets if m['market_id'] == market_id)
    sem = market['semantics']
    if not sem or sem['timeframe'] != 'daily' or sem['kind'] not in ('window_high', 'window_low'):
        raise ValueError('This first report supports daily hit markets only')
    start, end = epoch(sem['window_start']), epoch(sem['window_end'])
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
    rows = join_candles(points, candles)
    opening = Decimal(candles[0]['open'])
    threshold = Decimal(sem['threshold'])
    field = 'high' if sem['kind'] == 'window_high' else 'low'
    hits = [c for c in candles if (Decimal(c[field]) >= threshold if field == 'high' else Decimal(c[field]) <= threshold)]
    hit_text = ('Observed threshold crossing in candle beginning ' + datetime.fromtimestamp(hits[0]['open_time_ms']/1000, timezone.utc).isoformat()) if hits else ('No crossing in the complete saved window' if complete else 'No crossing observed; candle coverage incomplete')
    table = []
    for m in markets:
        s = m['semantics']
        if not s or s['window_start'] != sem['window_start'] or s['window_end'] != sem['window_end']:
            continue
        ps = usable_points(histories[m['market_id']], start, end)
        values = [Decimal(p['price']) for p in ps]
        distance = (Decimal(s['threshold']) / opening - 1) * 100
        price_range = f'{min(values):.4f}–{max(values):.4f}' if values else 'Missing'
        table.append((abs(distance), f'<tr><td>{escape(m["title"])}</td><td>{distance:+.2f}%</td><td>{price_range}</td><td>{len(ps)}</td></tr>'))
    low = min(float(c['low']) for c in candles)
    high = max(float(c['high']) for c in candles)
    lower, upper = min(low,float(threshold))-200, max(high,float(threshold))+200
    btc_chart = chart([(c['close_time_ms']/1000,c['close']) for c in candles],start,end,lower,upper,'#2563eb',threshold,max_gap=60,overlay=[(r['time'],r['price']) for r in rows])
    distance = (threshold/opening-1)*100
    title = escape(market['title'])
    provenance = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                  for name in ('markets.json', 'prices.json', 'btc.json')}
    provenance['script'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px system-ui;max-width:1080px;margin:35px auto;padding:0 20px;color:#172033}}svg{{width:100%;background:#f8fafc}}svg text{{font:12px system-ui;fill:#475569}}table{{border-collapse:collapse;width:100%}}td,th{{padding:9px;border-bottom:1px solid #ddd;text-align:left}}.note{{color:#475569}}input{{width:100%}}</style>
<h1>{title}</h1><p>{escape(sem["window_start"])} to {escape(sem["window_end"])} · UTC. Opening BTC/USDT: {opening:,.2f}. Threshold: {threshold:,.0f} ({distance:+.2f}% from opening).</p>
<h2>BTC and YES price</h2><p><span style="color:#2563eb">Blue: BTC/USDT one-minute closes (left axis)</span> · <span style="color:#0f766e">Green: YES five-minute price (right axis, 0–1)</span> · Red dashed: hit threshold. The source uses candle {field}s; closes alone do not establish a hit.</p>{btc_chart}
<p>Move the slider to inspect each five-minute observation. The vertical marker shows its bucket end; dots highlight YES and the latest completed BTC candle. The chart keeps the full day visible. Missing buckets remain disconnected.</p><label for="slider">Observation time</label><input id="slider" type="range" min="0" max="{len(rows)-1}" value="0"><p id="detail" aria-live="polite"></p>
<p>{escape(hit_text)}. Stored BTC range: {low:,.2f}–{high:,.2f}. Valid market buckets: {len(points)} / {(end-start)//300} possible daily slots.</p>
<h2>Other thresholds in this event</h2><p>Sorted by absolute distance from the opening spot price. Price ranges use the entire day and are descriptive only; they must not be used to select markets for a historical prediction.</p>
<table><thead><tr><th>Market</th><th>Opening distance</th><th>YES range</th><th>5-minute buckets</th></tr></thead><tbody>{''.join(row for _,row in sorted(table))}</tbody></table>
<p class="note">Market {market_id}; source: {escape(str(folder))}. Nearness to spot is a useful starting point, but direction, time remaining, volatility and whether the barrier has already been hit also matter. No distance filter is imposed.</p>
<p class="note">Exploratory description only. Price aggregation and historical rule versions remain unverified. Zero-width and incomplete-segment points are excluded. No accepted settlement label, executable quote, forecast or backtest is presented.</p>
<details><summary>Input provenance · report schema 1</summary><pre>{escape(json.dumps(provenance, indent=2))}</pre></details>
<script>const rows={json.dumps(rows)};const slider=document.getElementById('slider');
function show(){{
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
}}slider.addEventListener('input',show);show();</script></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)
    print(f'{output}: {len(points)} market buckets; {len(candles)} BTC candles; complete candle window={complete}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', default='1151848')
    parser.add_argument('--market', default='5422669')
    parser.add_argument('--data', type=Path, default=Path('data/bitcoin'))
    parser.add_argument('--output', type=Path, default=Path('data/analysis/market-preview.html'))
    args = parser.parse_args()
    render(args.data / args.event, args.market, args.output)


if __name__ == '__main__':
    main()
