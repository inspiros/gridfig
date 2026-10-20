// Gridfig's core API takes Typst content, so callers retain all of Typst's power.
#let figure-page(body, margin: 2mm) = {
  set page(width: auto, height: auto, margin: margin)
  body
}

#let gridfig(
  cells,
  top: none, left: none, bottom: none, right: none,
  cell-width: 28mm, cell-height: auto,
  gap: 1.5mm, header-gap: 2mm, side-width: 18mm,
  top-height: auto, bottom-height: auto,
  font: "Libertinus Serif", font-size: 9pt,
  rotations: (:), stroke: none,
) = {
  assert(cells.len() > 0, message: "gridfig needs at least one row")
  let nr = cells.len()
  let nc = cells.first().len()
  assert(nc > 0, message: "gridfig needs at least one column")
  assert(cells.all(row => row.len() == nc), message: "gridfig rows must have equal lengths")
  for (side, labels, count) in (("top", top, nc), ("bottom", bottom, nc), ("left", left, nr), ("right", right, nr)) {
    assert(labels == none or labels.len() == count, message: side + " header count does not match the grid")
  }
  let ch = if cell-height == auto { cell-width } else { cell-height }
  let columns = (if left != none { (side-width,) } else { () }) + (cell-width,) * nc + (if right != none { (side-width,) } else { () })
  let rows = (if top != none { (top-height,) } else { () }) + (ch,) * nr + (if bottom != none { (bottom-height,) } else { () })
  let cg = (if left != none { (header-gap,) } else { () }) + (gap,) * (nc - 1) + (if right != none { (header-gap,) } else { () })
  let rg = (if top != none { (header-gap,) } else { () }) + (gap,) * (nr - 1) + (if bottom != none { (header-gap,) } else { () })
  let label(value, side) = {
    let angle = rotations.at(side, default: 0deg)
    text(font: font, size: font-size, rotate(angle, reflow: true, value))
  }
  let children = ()
  if top != none {
    if left != none { children.push([]) }
    children += top.map(it => label(it, "top"))
    if right != none { children.push([]) }
  }
  for (i, row) in cells.enumerate() {
    if left != none { children.push(label(left.at(i), "left")) }
    for cell in row {
      children.push(block(width: cell-width, height: ch, clip: true, stroke: stroke, align(center + horizon, if cell == none { [] } else { cell })))
    }
    if right != none { children.push(label(right.at(i), "right")) }
  }
  if bottom != none {
    if left != none { children.push([]) }
    children += bottom.map(it => label(it, "bottom"))
    if right != none { children.push([]) }
  }
  block(breakable: false, grid(
    columns: columns, rows: rows,
    column-gutter: cg, row-gutter: rg,
    align: center + horizon, inset: 0pt,
    ..children,
  ))
}

// JSON labels are plain text unless explicitly wrapped in {"typst": "..."}.
// Evaluate rich labels only in projects you trust, as with ordinary Typst files.
#let config-label(value) = {
  if type(value) == dictionary { eval(value.typst, mode: "markup") } else { value }
}

#let gridfig-from-config(config, base: "") = {
  let opts = config.at("layout", default: (:))
  let headers = config.at("headers", default: (:))
  let labels(side) = {
    let values = headers.at(side, default: none)
    if values == none { none } else { values.map(config-label) }
  }
  let fit = opts.at("fit", default: "contain")
  let cells = config.images.map(row => row.map(path => {
    if path == none { none } else {
      image("/" + base + path, width: 100%, height: 100%, fit: fit)
    }
  }))
  let rotations = (:)
  for (side, angle) in opts.at("rotations", default: (:)) { rotations.insert(side, angle * 1deg) }
  let border = opts.at("stroke_pt", default: 0)
  gridfig(cells,
    top: labels("top"), bottom: labels("bottom"), left: labels("left"), right: labels("right"),
    cell-width: opts.at("cell_width_mm", default: 28) * 1mm,
    cell-height: opts.at("cell_height_mm", default: opts.at("cell_width_mm", default: 28)) * 1mm,
    gap: opts.at("gap_mm", default: 1.5) * 1mm,
    header-gap: opts.at("header_gap_mm", default: 2) * 1mm,
    side-width: opts.at("side_width_mm", default: 18) * 1mm,
    top-height: if opts.at("top_height_mm", default: none) == none { auto } else { opts.top_height_mm * 1mm },
    bottom-height: if opts.at("bottom_height_mm", default: none) == none { auto } else { opts.bottom_height_mm * 1mm },
    font: opts.at("font", default: "Libertinus Serif"),
    font-size: opts.at("font_size_pt", default: 9) * 1pt,
    rotations: rotations, stroke: if border > 0 { border * 1pt + luma(160) } else { none },
  )
}
