import json, re, os
D = os.path.dirname(os.path.abspath(__file__))
rd = lambda f: open(os.path.join(D, "src", f), encoding="utf-8").read()
assump = open("/home/claude/work/solar_rankine_lab/docs/assumptions.md", encoding="utf-8").read().strip()
assump += ("\n\n**Property data (browser edition).** R-134a properties come from tables generated with CoolProp (saturation: 0.5 K steps from -40 to 100 C; "
           "superheated vapor: offsets from saturated vapor on a 1 K by 1 K grid; effective liquid volume for the isentropic pump work), interpolated with cubic Hermite and bilinear schemes. "
           "The Validation page compares them with CoolProp reference values, and the daily results with those of the Python version of the lab.")
html = rd("template.html")
def put(tag, text):
    global html
    html = html.replace(f"/*__{tag}__*/", text.replace("</script", "<\\/script"), 1)
put("CSS", rd("style.css"))
put("TABLES", json.dumps(json.load(open(os.path.join(D, "src", "tables.json"))), separators=(",", ":")))
put("ASSUMPTIONS", json.dumps(assump))
put("CORE", rd("core.js")); put("VALIDATION", rd("validation.js")); put("CHARTS", rd("charts.js")); put("UI", rd("ui.js"))
out = os.path.join(D, "Solar_Rankine_Lab.html")
open(out, "w", encoding="utf-8").write(html)
print(out, os.path.getsize(out) // 1024, "KB")
