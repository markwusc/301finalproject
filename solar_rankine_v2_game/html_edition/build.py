"""Build the standalone HTML files.

    python build.py          -> Solar_Rankine_Lab.html      (legacy full edition: missions, comparison, validation)
    python build.py --web    -> Solar_Rankine_Lab_web.html  (v2 website: sandbox, game modes, scoreboard)
Property tables: run gen_tables.py first if src/tables.json is missing.
"""
import json, os, sys
WEB = "--web" in sys.argv
D = os.path.dirname(os.path.abspath(__file__))
rd = lambda f: open(os.path.join(D, "src", f), encoding="utf-8").read()
tables = json.dumps(json.load(open(os.path.join(D, "src", "tables.json"))), separators=(",", ":"))


def fill(html, tag, text):
    return html.replace(f"/*__{tag}__*/", text.replace("</script", "<\\/script"), 1)


if WEB:
    html = rd("template2.html")
    ui = rd("ui2.js").replace("/*__STAGE3__*/", rd("viz.js"), 1).replace("/*__STAGE4__*/", rd("feedback.js"), 1)
    for tag, text in (("CSS", rd("style.css") + "\n" + rd("style2.css")), ("TABLES", tables), ("CORE", rd("core.js")),
                      ("GAME", rd("game.js")), ("CHARTS", rd("charts.js")), ("UI", ui)):
        html = fill(html, tag, text)
    out = os.path.join(D, "..", "Solar_Rankine_Lab_web.html")
else:
    assump = open(os.path.join(D, "..", "app", "docs", "assumptions.md"), encoding="utf-8").read().strip()
    assump += ("\n\n**Property data (browser edition).** R-134a properties come from tables generated with CoolProp (saturation: 0.5 K steps from -40 to 100 C; "
               "superheated vapor: offsets from saturated vapor on a 1 K by 1 K grid; effective liquid volume for the isentropic pump work), interpolated with cubic Hermite and bilinear schemes.")
    html = rd("template.html")
    for tag, text in (("CSS", rd("style.css")), ("TABLES", tables), ("ASSUMPTIONS", json.dumps(assump)), ("CORE", rd("core.js")),
                      ("VALIDATION", rd("validation.js")), ("CHARTS", rd("charts.js")), ("UI", rd("ui.js"))):
        html = fill(html, tag, text)
    out = os.path.join(D, "..", "Solar_Rankine_Lab.html")
open(out, "w", encoding="utf-8").write(html)
print(os.path.normpath(out), os.path.getsize(out) // 1024, "KB")
