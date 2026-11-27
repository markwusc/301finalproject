import sys, json
from playwright.sync_api import sync_playwright
URL = "file:///home/claude/work/html/Solar_Rankine_Lab.html"
errs = []
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1500, "height": 1000})
    pg.on("console", lambda m: errs.append(("console." + m.type, m.text)) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append(("pageerror", str(e))))
    pg.goto(URL); pg.wait_for_timeout(500)
    pg.screenshot(path="shots/01_menu.png")
    def nav(name): pg.click(f'.navb[data-page="{name}"]'); pg.wait_for_timeout(700)
    nav("Free Play"); pg.screenshot(path="shots/02_freeplay_plant.png", full_page=True)
    pg.click('.tab:text("Day plots")'); pg.wait_for_timeout(400); pg.screenshot(path="shots/03_dayplots.png", full_page=True)
    pg.click('.tab:text("Cycle")'); pg.wait_for_timeout(400); pg.screenshot(path="shots/04_cycle.png", full_page=True)
    pg.click('.tab:text("Energy balance")'); pg.wait_for_timeout(400); pg.screenshot(path="shots/05_energy.png", full_page=True)
    pg.click('.tab:text("Data")'); pg.wait_for_timeout(300); pg.screenshot(path="shots/06_data.png")
    nav("Steady-State Calculator"); pg.screenshot(path="shots/07_steady.png", full_page=True)
    nav("Missions"); pg.click('button:text("Load a worked solution")') if pg.query_selector('summary') and (pg.click('summary:text("Hint and worked solution")') or True) else None
    pg.click('button:text("Load a worked solution")'); pg.wait_for_timeout(500); pg.screenshot(path="shots/08_mission_rankine.png", full_page=True)
    pg.select_option("select", "night"); pg.wait_for_timeout(500)
    pg.click('summary:text("Hint and worked solution")'); pg.click('button:text("Load a worked solution")'); pg.wait_for_timeout(900); pg.screenshot(path="shots/09_mission_night.png", full_page=True)
    nav("Comparison"); pg.wait_for_timeout(500); pg.screenshot(path="shots/10_compare.png", full_page=True)
    nav("Validation"); pg.wait_for_timeout(1500); pg.screenshot(path="shots/11_validation.png", full_page=True)
    nav("Assumptions"); pg.screenshot(path="shots/12_assumptions.png", full_page=True)
    b.close()
print("errors:", json.dumps(errs, indent=1) if errs else "none")
