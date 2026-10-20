#import "lib.typ": figure-page, gridfig-from-config
#let config-path = sys.inputs.at("config", default: "examples/comparison.json")
#let config = json(config-path)
#let parts = config-path.split("/").slice(0, -1)
#let base = if parts.len() == 0 { "" } else { parts.join("/") + "/" }
#show: figure-page.with(margin: config.at("layout", default: (:)).at("margin_mm", default: 2) * 1mm)
#gridfig-from-config(config, base: base)
