/* Geometry stays in millimeters; units change presentation, never the figure. */
(function (root) {
  "use strict";
  const mmPerUnit = {mm: 1, cm: 10, in: 25.4, pt: 25.4 / 72, px: 25.4 / 96};
  const natural = (a, b) => a.localeCompare(b, "en", {numeric: true, sensitivity: "base"}) || a.localeCompare(b);
  const toMM = (value, unit) => value * mmPerUnit[unit];
  const fromMM = (value, unit) => value / mmPerUnit[unit];
  const presets = {
    tight: {margin_mm:0, gap_mm:0, header_gap_mm:0, top_height_mm:null, bottom_height_mm:null},
    paper: {margin_mm:2, gap_mm:1.5, header_gap_mm:2, top_height_mm:8, bottom_height_mm:6},
    airy: {margin_mm:4, gap_mm:3, header_gap_mm:3, top_height_mm:10, bottom_height_mm:8},
  };
  function presetLayout(layout, name) {
    if (!presets[name]) throw Error("Unknown layout preset: " + name);
    return {...layout, ...presets[name]};
  }
  function matchingPreset(layout) {
    return Object.keys(presets).find(name => Object.entries(presets[name]).every(([key,value]) =>
      value === null ? layout[key] == null : typeof layout[key] === "number" && Math.abs(layout[key]-value)<1e-8)) || "custom";
  }
  function geometry(config) {
    const l = config.layout, nr = config.images.length, nc = config.images[0].length;
    const enabled = side => Array.isArray(config.headers[side]);
    const cw = l.cell_width_mm, ch = l.cell_height_mm, gap = l.gap_mm, hg = l.header_gap_mm, margin = l.margin_mm;
    // Fixed header regions are exact. Auto text metrics are an editing estimate.
    const autoHeight = l.font_size_pt * 25.4 / 72 * 1.35;
    const th = enabled("top") ? (l.top_height_mm ?? autoHeight) : 0;
    const bh = enabled("bottom") ? (l.bottom_height_mm ?? autoHeight) : 0;
    const lw = enabled("left") ? l.side_width_mm : 0, rw = enabled("right") ? l.side_width_mm : 0;
    const iw = nc * cw + (nc - 1) * gap, ih = nr * ch + (nr - 1) * gap;
    const x0 = margin + (enabled("left") ? lw + hg : 0), y0 = margin + (enabled("top") ? th + hg : 0);
    const regions = [];
    for (let r = 0; r < nr; r++) for (let c = 0; c < nc; c++) regions.push({kind: "image", r, c, x: x0 + c * (cw + gap), y: y0 + r * (ch + gap), w: cw, h: ch});
    for (const side of ["top", "bottom"]) if (enabled(side)) for (let c = 0; c < nc; c++) regions.push({kind: "header", side, index: c, x: x0 + c * (cw + gap), y: side === "top" ? margin : y0 + ih + hg, w: cw, h: side === "top" ? th : bh});
    for (const side of ["left", "right"]) if (enabled(side)) for (let r = 0; r < nr; r++) regions.push({kind: "header", side, index: r, x: side === "left" ? margin : x0 + iw + hg, y: y0 + r * (ch + gap), w: side === "left" ? lw : rw, h: ch});
    return {width: x0 + iw + (enabled("right") ? hg + rw : 0) + margin, height: y0 + ih + (enabled("bottom") ? hg + bh : 0) + margin, regions};
  }
  function methodFolderPlan(paths) {
    let parts = paths.map(path => path.replaceAll("\\", "/").split("/"));
    if (parts.every(p => p.length >= 3 && p[0] === parts[0][0])) parts = parts.map(p => p.slice(1));
    if (!parts.length || parts.some(p => p.length !== 2 || !p[0] || p[0].startsWith("."))) throw Error("Use method/sample.png folders (one method directory per column). Choose Flat list for other folder layouts.");
    const methods = [...new Set(parts.map(p => p[0]))].sort(natural);
    const samples = [...new Set(parts.map(p => p[1].replace(/\.[^.]+$/, "")))].sort(natural);
    if (methods.length > 20 || samples.length > 20 || methods.length * samples.length > 100) throw Error("Folder layout exceeds the limit of 20 rows/columns and 100 cells.");
    const matrix = samples.map(() => methods.map(() => null));
    parts.forEach(([method, file], index) => {
      const r = samples.indexOf(file.replace(/\.[^.]+$/, "")), c = methods.indexOf(method);
      if (matrix[r][c] !== null) throw Error(`Duplicate sample in ${method}: ${file}. Each sample stem must be unique within a method.`);
      matrix[r][c] = index;
    });
    return {methods, samples, matrix};
  }
  function normalizeTray(images, tray) {
    const placed=new Set(images.flat().filter(Boolean));
    const result=[...new Set(tray.filter(path=>path && !placed.has(path)))];
    if(result.length>200)throw Error("The tray supports 200 unused images. Remove some tray images before importing more.");
    return result;
  }
  function placeImports(state, paths, start=null, onlyTray=false) {
    const images=state.images.map(row=>row.slice()), displaced=[], slots=[];
    images.forEach((row,r)=>row.forEach((path,c)=>{
      if(!onlyTray && (start ? r*row.length+c>=start[0]*row.length+start[1] : !path))slots.push([r,c]);
    }));
    paths.slice(0,slots.length).forEach((path,index)=>{
      const [r,c]=slots[index];if(images[r][c])displaced.push(images[r][c]);images[r][c]=path;
    });
    return {images,tray:normalizeTray(images,[...(state.tray||[]),...displaced,...paths.slice(slots.length)])};
  }
  function moveImage(state, source, target) {
    const images=state.images.map(row=>row.slice()),tray=[...(state.tray||[])];
    if(source.kind==='grid' && target.kind==='grid') {
      [images[source.r][source.c],images[target.r][target.c]]=[images[target.r][target.c],images[source.r][source.c]];
    } else if(source.kind==='tray' && target.kind==='grid') {
      if(!Number.isInteger(source.index)||source.index<0||source.index>=tray.length)throw Error('This tray image is no longer available.');
      const old=images[target.r][target.c];images[target.r][target.c]=tray.splice(source.index,1)[0];
      if(old)tray.splice(source.index,0,old);
    } else if(source.kind==='grid' && target.kind==='tray') {
      const old=images[source.r][source.c];images[source.r][source.c]=null;
      if(old)tray.splice(target.index ?? tray.length,0,old);
    } else if(source.kind==='tray' && target.kind==='tray') {
      if(!Number.isInteger(source.index)||source.index<0||source.index>=tray.length)throw Error('This tray image is no longer available.');
      const path=tray.splice(source.index,1)[0];tray.splice(target.index ?? tray.length,0,path);
    } else throw Error('Unknown image move.');
    return {images,tray:normalizeTray(images,tray)};
  }
  function gridToTray(state) {
    const images=state.images.map(row=>row.map(()=>null));
    return {images,tray:normalizeTray(images,[...(state.tray||[]),...state.images.flat()])};
  }
  function clearImages(state) { return {images:state.images.map(row=>row.map(()=>null)),tray:[]}; }
  const api = {mmPerUnit, natural, toMM, fromMM, geometry, methodFolderPlan, presets, presetLayout, matchingPreset, normalizeTray, placeImports, moveImage, gridToTray, clearImages};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.GridfigModel = api;
})(globalThis);
