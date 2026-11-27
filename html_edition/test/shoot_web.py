import json
from playwright.sync_api import sync_playwright
errs = []
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1500, "height": 1000})
    pg.on("console", lambda m: errs.append(("console." + m.type, m.text)) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append(("pageerror", str(e))))
    pg.goto("file:///home/claude/work/html/Solar_Rankine_Lab_web.html"); pg.wait_for_timeout(800)
    print("nav:", pg.eval_on_selector_all(".navb", "e=>e.map(x=>x.textContent)"))
    print("done visible:", pg.is_visible("#done"))
    pg.screenshot(path="shots/w1_free.png", full_page=True)
    kp = lambda: pg.eval_on_selector_all(".kpis .metric, .kpis > div", "e=>e.slice(0,6).map(x=>x.innerText.replace(/\\n/g,' '))")
    print("baseline:", kp())
    # change collector area slider
    pg.evaluate("""()=>{const r=[...document.querySelectorAll('input[type=range]')].find(e=>e.offsetParent&&e.closest('label,div').innerText.includes('Collector area')); r.value=12; r.dispatchEvent(new Event('input',{bubbles:true})); r.dispatchEvent(new Event('change',{bubbles:true}));}"""); pg.wait_for_timeout(1000)
    print("area=12:", kp())
    pg.click('button:text("Reset all controls")'); pg.wait_for_timeout(800)
    print("after reset:", kp())
    pg.click('.plant ~ * button.btn, button.btn:text-is("Play")'); pg.wait_for_timeout(1500); print("play label:", pg.inner_text('button.btn:text-is("Pause")'), "| time:", pg.inner_text('text=/Solar time/')); pg.click('button.btn:text-is("Pause")')
    pg.screenshot(path="shots/w2_play.png")
    pg.click('.tab:text("Day plots")'); pg.wait_for_timeout(300)
    pg.hover('svg >> nth=0', position={"x":400,"y":80}); pg.wait_for_timeout(200)
    nav = pg.click('.navb[data-page="Steady-State Calculator"]'); pg.wait_for_timeout(600)
    print("steady:", pg.eval_on_selector_all(".kpis .metric, .kpis > div", "e=>e.map(x=>x.innerText.replace(/\\n/g,' '))"))
    pg.screenshot(path="shots/w3_steady.png", full_page=True)
    b.close()
print("errors:", json.dumps(errs, indent=1) if errs else "none")
