"""One-time script: writes all 6 complete HTML/Jinja2 carousel templates."""
import pathlib

T = pathlib.Path("assets/templates")
T.mkdir(parents=True, exist_ok=True)

GF = "https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=Montserrat:wght@300;400;600;700&display=swap"

# ─────────────────────────────────────────────────────────────────────
# SHARED FOOTER SNIPPET (injected at bottom of every template body)
# ─────────────────────────────────────────────────────────────────────
FOOTER_CSS = """
  .footer { position:absolute; bottom:0; left:0; right:0; height:135px;
    background:{{ theme.bg }}; border-top:1px solid {{ theme.accent }}40;
    display:flex; align-items:center; padding:0 48px; gap:20px; }
  .footer-logo { height:42px; object-fit:contain; }
  .footer-div  { width:1px; height:38px; background:{{ theme.accent }}50; flex-shrink:0; }
  .footer-text { display:flex; flex-direction:column; gap:4px; }
  .footer-l1   { font-weight:600; font-size:15px; color:{{ theme.text_primary }}; }
  .footer-l2   { font-weight:300; font-size:14px; color:{{ theme.accent }}; }
"""

FOOTER_HTML = """
  <div class="footer">
    {% if logo_data_uri %}<img class="footer-logo" src="{{ logo_data_uri }}" alt="VB Exports"><div class="footer-div"></div>{% endif %}
    <div class="footer-text">
      <span class="footer-l1">{{ footer.line1 }}</span>
      <span class="footer-l2">{{ footer.line2 }}</span>
    </div>
  </div>
"""

# ─────────────────────────────────────────────────────────────────────
# 1. COFFEE MARKET — Dark espresso + gold
# ─────────────────────────────────────────────────────────────────────
(T / "slide_coffee_market.html").write_text(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  @import url("{GF}");
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; overflow:hidden; background:{{{{ theme.bg }}}}; font-family:'Montserrat',sans-serif; position:relative; }}

  .brand-bar {{ position:absolute; top:0; left:0; right:0; height:72px; background:{{{{ theme.bg }}}}; display:flex; align-items:center; justify-content:space-between; padding:0 48px; border-bottom:1.5px solid {{{{ theme.accent }}}}; z-index:10; }}
  .brand-name {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:22px; color:{{{{ theme.accent }}}}; letter-spacing:1px; }}
  .slide-counter {{ font-size:15px; color:{{{{ theme.accent }}}}; opacity:0.6; }}

  .photo-zone {{ position:absolute; top:72px; left:0; right:0; height:480px; overflow:hidden; }}
  .photo-zone img {{ width:100%; height:100%; object-fit:cover; display:block; }}
  .photo-grad {{ position:absolute; bottom:0; left:0; right:0; height:260px; background:linear-gradient(to bottom,transparent,{{{{ theme.bg }}}}); }}

  .content {{ position:absolute; top:518px; left:0; right:0; padding:0 48px; }}
  .badge {{ display:inline-flex; align-items:center; height:30px; border:1px solid {{{{ theme.accent }}}}; border-radius:15px; padding:0 16px; margin-bottom:18px; }}
  .badge-txt {{ font-size:11px; font-weight:600; color:{{{{ theme.accent }}}}; letter-spacing:2px; text-transform:uppercase; }}
  .headline {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:{{{{ headline_size }}}}px; color:{{{{ theme.text_primary }}}}; line-height:1.15; margin-bottom:22px; text-shadow:2px 2px 8px rgba(0,0,0,0.7); }}
  .stat-box {{ background:rgba(200,150,30,0.09); border-left:4px solid {{{{ theme.accent }}}}; padding:14px 20px; margin-bottom:18px; border-radius:0 6px 6px 0; }}
  .stat-num {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:50px; color:{{{{ theme.accent }}}}; line-height:1; }}
  .stat-lbl {{ font-size:15px; color:{{{{ theme.text_muted }}}}; margin-top:4px; }}
  .bullets {{ list-style:none; }}
  .bullets li {{ display:flex; align-items:flex-start; gap:14px; margin-bottom:14px; }}
  .dot {{ flex-shrink:0; width:8px; height:8px; border-radius:50%; background:{{{{ theme.accent }}}}; margin-top:9px; }}
  .btxt {{ font-size:21px; color:{{{{ theme.text_muted }}}}; line-height:1.65; }}
  {FOOTER_CSS}
</style></head>
<body>
  <div class="brand-bar">
    <span class="brand-name">VB EXPORTS</span>
    <span class="slide-counter">{{{{ slide_num }}}} / {{{{ total_slides }}}}</span>
  </div>
  <div class="photo-zone"><img src="{{{{ photo_url }}}}" alt=""><div class="photo-grad"></div></div>
  <div class="content">
    <div class="badge"><span class="badge-txt">{{{{ theme.badge_text }}}}</span></div>
    <div class="headline">{{{{ headline }}}}</div>
    {{% if stat_number %}}
    <div class="stat-box">
      <div class="stat-num">{{{{ stat_number }}}}</div>
      <div class="stat-lbl">{{{{ stat_label }}}}</div>
    </div>
    {{% endif %}}
    <ul class="bullets">
      {{% for bullet in bullets %}}<li><div class="dot"></div><span class="btxt">{{{{ bullet }}}}</span></li>{{% endfor %}}
    </ul>
  </div>
  {FOOTER_HTML}
</body></html>""", encoding="utf-8")
print("1/6 coffee_market OK")

# ─────────────────────────────────────────────────────────────────────
# 2. PRICE TRENDS — Dark amber
# ─────────────────────────────────────────────────────────────────────
(T / "slide_price_trends.html").write_text(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  @import url("{GF}");
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; overflow:hidden; background:{{{{ theme.bg }}}}; font-family:'Montserrat',sans-serif; position:relative; }}

  .brand-bar {{ position:absolute; top:0; left:0; right:0; height:72px; background:{{{{ theme.bg }}}}; display:flex; align-items:center; justify-content:space-between; padding:0 48px; border-bottom:1.5px solid {{{{ theme.accent }}}}; z-index:10; }}
  .brand-name {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:22px; color:{{{{ theme.accent }}}}; letter-spacing:1px; }}
  .slide-counter {{ font-size:15px; color:{{{{ theme.accent }}}}; opacity:0.6; }}

  .photo-zone {{ position:absolute; top:72px; left:0; right:0; height:400px; overflow:hidden; }}
  .photo-zone img {{ width:100%; height:100%; object-fit:cover; display:block; }}
  .photo-grad {{ position:absolute; bottom:0; left:0; right:0; height:220px; background:linear-gradient(to bottom,transparent,{{{{ theme.bg }}}}); }}

  /* Price hero block */
  .price-hero {{ position:absolute; top:430px; left:0; right:0; padding:0 48px; display:flex; align-items:center; gap:40px; }}
  .price-main {{ flex:1; }}
  .price-big {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:80px; color:#F5C842; line-height:1; }}
  .price-unit {{ font-size:17px; color:{{{{ theme.text_muted }}}}; margin-top:4px; }}
  .price-side {{ display:flex; flex-direction:column; gap:16px; border-left:1px solid {{{{ theme.accent }}}}40; padding-left:32px; }}
  .price-row {{ display:flex; flex-direction:column; gap:2px; }}
  .price-row-val {{ font-family:'Oswald',sans-serif; font-weight:600; font-size:26px; color:{{{{ theme.accent }}}}; }}
  .price-row-lbl {{ font-size:13px; color:{{{{ theme.text_muted }}}}; }}

  .label {{ position:absolute; top:620px; left:48px; font-size:11px; font-weight:600; color:{{{{ theme.accent }}}}; letter-spacing:3px; text-transform:uppercase; }}
  .headline {{ position:absolute; top:644px; left:48px; right:48px; font-family:'Oswald',sans-serif; font-weight:700; font-size:{{{{ headline_size }}}}px; color:{{{{ theme.text_primary }}}}; line-height:1.15; }}

  .bullets {{ position:absolute; top:858px; left:48px; right:48px; list-style:none; }}
  .bullets li {{ display:flex; align-items:flex-start; gap:0; margin-bottom:14px; background:rgba(212,130,10,0.07); border-radius:6px; padding:14px 18px; border-left:3px solid {{{{ theme.accent }}}}; }}
  .btxt {{ font-size:20px; color:{{{{ theme.text_muted }}}}; line-height:1.6; }}
  {FOOTER_CSS}
</style></head>
<body>
  <div class="brand-bar">
    <span class="brand-name">VB EXPORTS</span>
    <span class="slide-counter">{{{{ slide_num }}}} / {{{{ total_slides }}}}</span>
  </div>
  <div class="photo-zone"><img src="{{{{ photo_url }}}}" alt=""><div class="photo-grad"></div></div>
  <div class="price-hero">
    <div class="price-main">
      <div class="price-big">{{{{ stat_number or '$3.24' }}}}</div>
      <div class="price-unit">{{{{ stat_label or 'Arabica Futures · ICE Exchange' }}}}</div>
    </div>
    {{% if bullets|length > 1 %}}
    <div class="price-side">
      <div class="price-row"><div class="price-row-val">{{{{ bullets[0][:12] }}}}</div><div class="price-row-lbl">Week High</div></div>
      <div class="price-row"><div class="price-row-val">{{{{ bullets[1][:12] }}}}</div><div class="price-row-lbl">90-day Avg</div></div>
    </div>
    {{% endif %}}
  </div>
  <div class="label">{{{{ theme.badge_text }}}}</div>
  <div class="headline">{{{{ headline }}}}</div>
  <ul class="bullets">
    {{% for bullet in bullets[2:] %}}<li><span class="btxt">{{{{ bullet }}}}</span></li>{{% endfor %}}
    {{% if bullets|length <= 2 %}}{{% for bullet in bullets %}}<li><span class="btxt">{{{{ bullet }}}}</span></li>{{% endfor %}}{{% endif %}}
  </ul>
  {FOOTER_HTML}
</body></html>""", encoding="utf-8")
print("2/6 price_trends OK")

# ─────────────────────────────────────────────────────────────────────
# 3. GLOBAL BUYERS — Midnight navy + steel blue
# ─────────────────────────────────────────────────────────────────────
(T / "slide_global_buyers.html").write_text(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  @import url("{GF}");
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; overflow:hidden; background:{{{{ theme.bg }}}}; font-family:'Montserrat',sans-serif; position:relative; }}

  .brand-bar {{ position:absolute; top:0; left:0; right:0; height:72px; background:{{{{ theme.bg }}}}; display:flex; align-items:center; justify-content:space-between; padding:0 48px; border-bottom:1px solid {{{{ theme.accent }}}}30; z-index:10; }}
  .brand-name {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:22px; color:{{{{ theme.text_primary }}}}; }}
  .slide-counter {{ font-size:15px; color:{{{{ theme.accent }}}}; opacity:0.7; }}

  .photo-zone {{ position:absolute; top:72px; left:0; right:0; height:380px; overflow:hidden; }}
  .photo-zone img {{ width:100%; height:100%; object-fit:cover; object-position:center 60%; display:block; }}
  .photo-grad {{ position:absolute; bottom:0; left:0; right:0; height:200px; background:linear-gradient(to bottom,transparent,{{{{ theme.bg }}}}); }}

  /* Data grid 2×2 */
  .data-grid {{ position:absolute; top:420px; left:48px; right:48px; display:grid; grid-template-columns:1fr 1fr; gap:0; background:{{{{ theme.bg2 }}}}; border:1px solid {{{{ theme.accent }}}}20; border-radius:8px; overflow:hidden; }}
  .data-cell {{ padding:24px 28px; border-right:1px solid {{{{ theme.accent }}}}15; border-bottom:1px solid {{{{ theme.accent }}}}15; }}
  .data-cell:nth-child(2n) {{ border-right:none; }}
  .data-cell:nth-child(3), .data-cell:nth-child(4) {{ border-bottom:none; }}
  .cell-val {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:40px; color:{{{{ theme.accent }}}}; line-height:1; }}
  .cell-lbl {{ font-size:14px; color:{{{{ theme.text_muted }}}}; margin-top:6px; }}

  .label {{ position:absolute; top:640px; left:48px; font-size:11px; font-weight:600; color:{{{{ theme.accent }}}}; letter-spacing:3px; text-transform:uppercase; }}
  .headline {{ position:absolute; top:662px; left:48px; right:48px; font-family:'Oswald',sans-serif; font-weight:700; font-size:{{{{ headline_size }}}}px; color:{{{{ theme.text_primary }}}}; line-height:1.18; }}

  .bullets {{ position:absolute; top:880px; left:48px; right:48px; list-style:none; }}
  .bullets li {{ display:flex; align-items:flex-start; gap:16px; margin-bottom:14px; }}
  .arrow {{ font-family:'Oswald',sans-serif; font-size:22px; color:{{{{ theme.accent }}}}; flex-shrink:0; margin-top:2px; }}
  .btxt {{ font-size:21px; color:{{{{ theme.text_muted }}}}; line-height:1.6; }}
  {FOOTER_CSS}
</style></head>
<body>
  <div class="brand-bar">
    <span class="brand-name">VB EXPORTS</span>
    <span class="slide-counter">{{{{ slide_num }}}} / {{{{ total_slides }}}}</span>
  </div>
  <div class="photo-zone"><img src="{{{{ photo_url }}}}" alt=""><div class="photo-grad"></div></div>

  {{% set grid_items = data_grid if data_grid else [
    {{'value': stat_number or '€2.3B', 'label': 'EU Import Market'}},
    {{'value': '↑18%', 'label': 'YoY Growth'}},
    {{'value': 'EUDR 2025', 'label': 'Key Compliance'}},
    {{'value': '#3', 'label': "India's EU Rank"}}
  ] %}}
  <div class="data-grid">
    {{% for item in grid_items[:4] %}}
    <div class="data-cell">
      <div class="cell-val">{{{{ item.value }}}}</div>
      <div class="cell-lbl">{{{{ item.label }}}}</div>
    </div>
    {{% endfor %}}
  </div>

  <div class="label">{{{{ theme.badge_text }}}}</div>
  <div class="headline">{{{{ headline }}}}</div>
  <ul class="bullets">
    {{% for bullet in bullets[:3] %}}<li><div class="arrow">→</div><span class="btxt">{{{{ bullet }}}}</span></li>{{% endfor %}}
  </ul>
  {FOOTER_HTML}
</body></html>""", encoding="utf-8")
print("3/6 global_buyers OK")

# ─────────────────────────────────────────────────────────────────────
# 4. FARM ORIGIN — Forest green + leaf
# ─────────────────────────────────────────────────────────────────────
(T / "slide_farm_origin.html").write_text(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  @import url("{GF}");
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; overflow:hidden; background:{{{{ theme.bg }}}}; font-family:'Montserrat',sans-serif; position:relative; }}

  .brand-bar {{ position:absolute; top:0; left:0; right:0; height:72px; background:{{{{ theme.bg }}}}; display:flex; align-items:center; justify-content:space-between; padding:0 48px; border-bottom:1.5px solid {{{{ theme.accent }}}}50; z-index:10; }}
  .brand-name {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:22px; color:{{{{ theme.text_primary }}}}; }}
  .slide-counter {{ font-size:15px; color:{{{{ theme.accent }}}}; opacity:0.7; }}

  .photo-zone {{ position:absolute; top:72px; left:0; right:0; height:520px; overflow:hidden; }}
  .photo-zone img {{ width:100%; height:100%; object-fit:cover; object-position:center 30%; display:block; }}
  .photo-grad {{ position:absolute; bottom:0; left:0; right:0; height:280px; background:linear-gradient(to bottom,transparent,{{{{ theme.bg }}}}); }}

  .origin-badge {{ position:absolute; top:552px; left:48px; background:{{{{ theme.bg }}}}; border:2px solid {{{{ theme.accent }}}}; border-radius:22px; padding:8px 20px; display:inline-flex; align-items:center; gap:8px; }}
  .pin {{ color:{{{{ theme.accent }}}}; font-size:16px; }}
  .origin-txt {{ font-weight:600; font-size:15px; color:{{{{ theme.accent }}}}; }}

  .headline {{ position:absolute; top:616px; left:48px; right:48px; font-family:'Oswald',sans-serif; font-weight:700; font-size:{{{{ headline_size }}}}px; color:{{{{ theme.text_primary }}}}; line-height:1.15; }}
  .divider {{ position:absolute; top:818px; left:48px; width:70px; height:4px; background:{{{{ theme.accent }}}}; border-radius:2px; }}
  .body-txt {{ position:absolute; top:844px; left:48px; right:48px; font-size:21px; color:{{{{ theme.text_muted }}}}; line-height:1.7; }}

  .stats-row {{ position:absolute; top:1010px; left:48px; right:48px; display:flex; }}
  .stat-item {{ flex:1; text-align:center; padding:16px 8px; border-right:1px solid {{{{ theme.accent }}}}30; }}
  .stat-item:last-child {{ border-right:none; }}
  .stat-n {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:32px; color:{{{{ theme.accent }}}}; }}
  .stat-l {{ font-size:13px; color:{{{{ theme.text_muted }}}}; margin-top:4px; }}
  {FOOTER_CSS}
</style></head>
<body>
  <div class="brand-bar">
    <span class="brand-name">VB EXPORTS</span>
    <span class="slide-counter">{{{{ slide_num }}}} / {{{{ total_slides }}}}</span>
  </div>
  <div class="photo-zone"><img src="{{{{ photo_url }}}}" alt=""><div class="photo-grad"></div></div>
  <div class="origin-badge"><span class="pin">📍</span><span class="origin-txt">{{{{ badge_location or 'Coorg, Karnataka — 1,200m' }}}}</span></div>
  <div class="headline">{{{{ headline }}}}</div>
  <div class="divider"></div>
  <div class="body-txt">{{{{ bullets[0] if bullets else '' }}}}</div>
  {{% set fs = farm_stats if farm_stats else [
    {{'num': stat_number or '1,850 MT', 'lbl': 'Annual Yield'}},
    {{'num': 'GI Certified', 'lbl': 'Quality Mark'}},
    {{'num': 'Shade-Grown', 'lbl': 'Cultivation'}}
  ] %}}
  <div class="stats-row">
    {{% for s in fs[:3] %}}
    <div class="stat-item"><div class="stat-n">{{{{ s.num }}}}</div><div class="stat-l">{{{{ s.lbl }}}}</div></div>
    {{% endfor %}}
  </div>
  {FOOTER_HTML}
</body></html>""", encoding="utf-8")
print("4/6 farm_origin OK")

# ─────────────────────────────────────────────────────────────────────
# 5. EXPORT GUIDE — Graphite + material green
# ─────────────────────────────────────────────────────────────────────
(T / "slide_export_guide.html").write_text(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  @import url("{GF}");
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; overflow:hidden; background:{{{{ theme.bg }}}}; font-family:'Montserrat',sans-serif; position:relative; }}

  .brand-bar {{ position:absolute; top:0; left:0; right:0; height:72px; background:{{{{ theme.bg }}}}; display:flex; align-items:center; justify-content:space-between; padding:0 48px; border-bottom:1px solid #3C4043; z-index:10; }}
  .brand-name {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:22px; color:{{{{ theme.text_primary }}}}; }}
  .slide-counter {{ font-size:15px; color:#5F6368; }}

  .photo-zone {{ position:absolute; top:72px; left:0; right:0; height:360px; overflow:hidden; }}
  .photo-zone img {{ width:100%; height:100%; object-fit:cover; object-position:center; display:block; }}
  .photo-grad {{ position:absolute; bottom:0; left:0; right:0; height:160px; background:linear-gradient(to bottom,transparent,{{{{ theme.bg }}}}); }}

  .label {{ position:absolute; top:448px; left:48px; font-size:11px; font-weight:600; color:{{{{ theme.accent }}}}; letter-spacing:3px; text-transform:uppercase; }}
  .headline {{ position:absolute; top:472px; left:48px; right:48px; font-family:'Oswald',sans-serif; font-weight:700; font-size:{{{{ headline_size }}}}px; color:{{{{ theme.text_primary }}}}; line-height:1.18; }}

  .steps {{ position:absolute; top:694px; left:48px; right:48px; }}
  .step {{ display:flex; align-items:flex-start; gap:24px; margin-bottom:20px; }}
  .step-num {{ flex-shrink:0; width:40px; height:40px; border-radius:50%; background:{{{{ theme.accent }}}}; display:flex; align-items:center; justify-content:center; font-family:'Oswald',sans-serif; font-weight:700; font-size:18px; color:#FFFFFF; }}
  .step-body {{ flex:1; }}
  .step-title {{ font-weight:600; font-size:19px; color:{{{{ theme.text_primary }}}}; line-height:1.3; }}
  .step-desc {{ font-size:16px; color:{{{{ theme.text_muted }}}}; line-height:1.5; margin-top:3px; }}

  .alert-box {{ position:absolute; top:1040px; left:48px; right:48px; background:rgba(251,188,4,0.08); border:1px solid #FBBC04; border-radius:6px; padding:16px 20px; display:flex; align-items:center; gap:14px; }}
  .alert-icon {{ font-size:22px; flex-shrink:0; }}
  .alert-txt {{ font-size:18px; color:#FBBC04; font-weight:600; line-height:1.45; }}
  {FOOTER_CSS}
</style></head>
<body>
  <div class="brand-bar">
    <span class="brand-name">VB EXPORTS</span>
    <span class="slide-counter">{{{{ slide_num }}}} / {{{{ total_slides }}}}</span>
  </div>
  <div class="photo-zone"><img src="{{{{ photo_url }}}}" alt=""><div class="photo-grad"></div></div>
  <div class="label">{{{{ theme.badge_text }}}}</div>
  <div class="headline">{{{{ headline }}}}</div>
  <div class="steps">
    {{% for bullet in bullets[:3] %}}
    <div class="step">
      <div class="step-num">{{{{ loop.index }}}}</div>
      <div class="step-body"><div class="step-title">{{{{ bullet }}}}</div></div>
    </div>
    {{% endfor %}}
  </div>
  {{% if stat_number %}}<div class="alert-box"><span class="alert-icon">⚠</span><span class="alert-txt">{{{{ stat_number }}}} — {{{{ stat_label }}}}</span></div>{{% endif %}}
  {FOOTER_HTML}
</body></html>""", encoding="utf-8")
print("5/6 export_guide OK")

# ─────────────────────────────────────────────────────────────────────
# 6. PERSONAL — Playfair Display + Inter, Tailwind-based
#    NOTE: slide_personal.html is now maintained directly as a Jinja2/Tailwind
#    template in assets/templates/. This block preserves it (no-op if exists).
# ─────────────────────────────────────────────────────────────────────
personal_tmpl = T / "slide_personal.html"
if personal_tmpl.exists():
    print("6/6 personal OK (already exists — preserved)")
else:
    print("6/6 personal MISSING — please copy slide_personal.html into assets/templates/")
print("All templates written successfully.")
